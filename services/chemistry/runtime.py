from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import time
from typing import Callable

import numpy as np

from openmolspec_ui.config import ModelAssets
from openmolspec_ui.spectra import SpectralInput

from .errors import ChemistryError
from .schemas import JobRequest, ParseSpectrumRequest, StructureRequest
from .spectrum import legacy_spectrum, normalize_model_input, parse_upload, spectrum_record
from .store import ChemistryStore, json_value


TERMINAL = {"succeeded", "failed", "cancelled"}


def _validate_xyz(text: str) -> None:
    lines = text.splitlines()
    try:
        count = int(lines[0].strip())
        if count <= 0 or len(lines) < count + 2 or any(line.strip() for line in lines[count + 2:]):
            raise ValueError
        for line in lines[2:count + 2]:
            parts = line.split()
            if len(parts) != 4 or not all(math.isfinite(float(value)) for value in parts[1:]):
                raise ValueError
    except (ValueError, IndexError) as error:
        raise ValueError("XYZ must declare its atom count and contain finite x/y/z coordinates for every atom.") from error


def _molecule_applicability(mol) -> dict:
    from rdkit import Chem

    if mol is None:
        return {"model_eligible": False, "elements": [], "reasons": ["The saved conformer cannot be read."]}
    elements = sorted({atom.GetSymbol() for atom in mol.GetAtoms()})
    # Conservative service policy for neutral, closed-shell organic conformers.
    # Passing this gate does not establish checkpoint coverage or accuracy.
    unsupported = set(elements) - {"H", "C", "N", "O", "F", "P", "S", "Cl", "Br", "I"}
    reasons: list[str] = []
    if unsupported:
        reasons.append("Elements outside the service's organic model scope: " + ", ".join(sorted(unsupported)) + ".")
    if Chem.GetFormalCharge(mol) or any(atom.GetNumRadicalElectrons() for atom in mol.GetAtoms()):
        reasons.append("The models require a neutral, closed-shell structure.")
    if len(Chem.GetMolFrags(mol)) != 1:
        reasons.append("The models require a single connected molecule.")
    if mol.GetNumAtoms() < 3:
        reasons.append("The vibrational model requires at least three atoms including hydrogens.")
    return {"model_eligible": not reasons, "elements": elements, "reasons": reasons}


def _resolve_structure(request: StructureRequest) -> dict:
    from rdkit import Chem
    from rdkit.Chem import Descriptors
    from openmolspec_ui.chemistry import MoleculeInput, molecule_from_smiles, molecule_from_xyz, molecule_svg

    if request.xyz is not None:
        _validate_xyz(request.xyz)
        molecule = molecule_from_xyz(request.xyz.rstrip() + "\n")
    else:
        molecule = molecule_from_smiles(request.smiles.strip())
    if not molecule.atoms or not np.isfinite(molecule.mol.GetConformer().GetPositions()).all():
        raise ValueError("Structure has no atoms or contains invalid coordinates.")
    Chem.SanitizeMol(molecule.mol)
    # The legacy SVG helper computes 2D coordinates in place. Never draw the model's conformer.
    molblock = Chem.MolToMolBlock(molecule.mol)
    xyz = Chem.MolToXYZBlock(molecule.mol)
    heavy = Chem.RemoveHs(molecule.mol)
    return {
        "smiles": molecule.smiles,
        "formula": molecule.formula,
        "molecular_weight": float(Descriptors.MolWt(heavy)),
        "atom_count": molecule.atoms,
        "inchi_key": Chem.MolToInchiKey(heavy),
        "molblock": molblock,
        "xyz": xyz,
        "applicability": _molecule_applicability(molecule.mol),
        "svg": molecule_svg(MoleculeInput(Chem.Mol(molecule.mol), molecule.source)),
    }


class ChemistryRuntime:
    def __init__(self, store: ChemistryStore, assets: ModelAssets, *, device: str | None = None,
                 service_factory: Callable | None = None):
        self.store, self.assets = store, assets
        self.requested_device = device or os.environ.get("OPENMOLSPEC_DEVICE", "auto")
        self._device: str | None = None
        self._device_lock = asyncio.Lock()
        self._service_factory, self._service = service_factory, None
        self._wake = asyncio.Event()
        self._worker: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        self.store.recover_interrupted()
        self._worker = asyncio.create_task(self._work(), name="chemistry-calculations")
        self._wake.set()

    async def close(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._worker is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._worker), timeout=2)
            except asyncio.TimeoutError:
                # A native numerical call cannot be killed safely. Its cancelled
                # waiter cannot commit a result after shutdown; the job is explicit.
                self._worker.cancel()
                await asyncio.gather(self._worker, return_exceptions=True)
        self.store.close()

    async def device(self) -> str:
        if self._device is None:
            async with self._device_lock:
                if self._device is None:
                    if self.requested_device == "auto":
                        from openmolspec_ui.inference import resolve_device
                        self._device = await asyncio.to_thread(resolve_device, "auto")
                    else:
                        self._device = self.requested_device
        return self._device

    def _capabilities(self, device: str) -> dict:
        assets = self.assets
        exists = lambda path: path is not None and path.is_file()
        requirements = {
            "Hessian Hi": assets.hessian_hi_checkpoint,
            "Hessian Hij": assets.hessian_hij_checkpoint,
            "dipole response": assets.dedipole_checkpoint,
            "polarizability response": assets.depolar_checkpoint,
            "H/C NMR": assets.nmr_checkpoint,
        }
        missing = [name for name, path in requirements.items() if not exists(path)]
        gap_code = assets.root / "benchmarks/models/vib2conf/model.py"
        for name, checkpoint in list(requirements.items())[:4]:
            if exists(checkpoint) and not (checkpoint.parent.parent / "resolved_config.yaml").is_file():
                missing.append(f"{name} resolved_config.yaml")
        for module in ("models/equiformer_v3/hessian.py", "models/equiformer_v3/nmr.py",
                       "engines/hessian_physics.py"):
            if not (assets.root / "benchmarks" / module).is_file():
                missing.append(f"benchmarks/{module}")
        dataset = exists(assets.spectrum_lmdb)
        cached_generation = dataset and exists(assets.generation_predictions)
        setting = os.environ.get("OPENMOLSPEC_VIB2MOL_DIRECT", "auto").lower()
        direct = setting in {"1", "true", "on"} or (setting == "auto" and device.startswith("cuda"))
        vib2mol = assets.root / "benchmarks/models/vib2mol"
        direct_generation = (direct and exists(assets.generation_checkpoint)
                             and exists(assets.nmr_normalizer)
                             and (vib2mol / "train_entry.py").is_file()
                             and (vib2mol / "evaluate_multimodal.py").is_file()
                             and (vib2mol / "upstream/models/MolTokenizer").is_dir())
        gap = exists(assets.gap_checkpoint) and gap_code.is_file()
        return {
            "device": device, "root": str(assets.root), "domain": "theoretical",
            "capabilities": {
                "predict_spectra": {"available": not missing,
                    "detail": "Equiformer Hessian/response and H/C NMR; harmonic theoretical spectra" if not missing
                    else "Missing: " + ", ".join(missing)},
                "retrieve": {"available": dataset, "detail":
                    "OpenMolSpec theoretical test-set retrieval; actual backend is recorded per result" if dataset
                    else "Missing OpenMolSpec theoretical test-set LMDB"},
                "predict_gap": {"available": gap, "detail":
                    "Vib2Conf theoretical HOMO–LUMO gap (eV)" if gap
                    else "Missing gap checkpoint or upstream Vib2Conf implementation"},
                "generate": {"available": bool(cached_generation or direct_generation), "detail":
                    "Vib2Mol direct beam search; cached fallback recorded in provenance" if direct_generation
                    else "Vib2Mol cached theoretical test-set candidates selected by spectral neighbors" if cached_generation
                    else "Missing direct generation assets or theoretical reference LMDB/generation cache"},
            },
        }

    async def capabilities(self) -> dict:
        return self._capabilities(await self.device())

    async def resolve_molecule(self, owner_id: str, request: StructureRequest) -> dict:
        try:
            payload = await asyncio.to_thread(_resolve_structure, request)
        except (ValueError, RuntimeError) as error:
            raise ChemistryError("invalid_molecule", str(error)) from error
        return self.store.save_molecule(owner_id, payload)

    async def parse_spectrum(self, owner_id: str, request: ParseSpectrumRequest) -> dict:
        try:
            payload = await asyncio.to_thread(parse_upload, request)
        except ValueError as error:
            raise ChemistryError("invalid_spectrum", str(error)) from error
        return self.store.save_spectrum(owner_id, payload)

    def spectrum(self, owner_id: str, identifier: str) -> dict:
        spectrum = self.store.get_spectrum(owner_id, identifier)
        if spectrum is None:
            raise ChemistryError("not_found", "Spectrum was not found.", 404)
        return legacy_spectrum(spectrum)

    def molecule(self, owner_id: str, identifier: str) -> dict:
        molecule = self.store.get_molecule(owner_id, identifier)
        if molecule is None:
            raise ChemistryError("not_found", "Saved molecule was not found.", 404)
        if "applicability" not in molecule:
            from rdkit import Chem
            mol = Chem.MolFromMolBlock(molecule["molblock"], removeHs=False)
            molecule["applicability"] = _molecule_applicability(mol)
        return molecule

    async def submit(self, owner_id: str, request: JobRequest, *, source: str) -> dict:
        inputs = request.inputs.model_dump(exclude_none=True)
        fingerprint = None
        new_molecule = None
        if request.request_id is not None:
            payload = json.dumps([request.operation, inputs], sort_keys=True, separators=(",", ":"), allow_nan=False)
            fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            existing = self.store.replay_job(owner_id, request.request_id, fingerprint)
            if existing is not None:
                return existing
        if request.operation == "predict_spectra":
            if request.inputs.molecule_id is not None:
                molecule = self.molecule(owner_id, request.inputs.molecule_id)
            else:
                structure = StructureRequest(smiles=request.inputs.smiles, xyz=request.inputs.xyz)
                try:
                    molecule = await asyncio.to_thread(_resolve_structure, structure)
                except (ValueError, RuntimeError) as error:
                    raise ChemistryError("invalid_molecule", str(error)) from error
                new_molecule = molecule
            applicability = molecule["applicability"]
            if not applicability["model_eligible"]:
                raise ChemistryError("molecule_not_eligible", " ".join(applicability["reasons"]), 422)
            # Snapshot the immutable conformer used by this job.
            if new_molecule is None:
                inputs["molecule"] = {key: value for key, value in molecule.items() if key != "svg"}
        else:
            for modality in ("ir", "raman"):
                identifier = inputs.get(f"{modality}_id")
                if identifier is not None:
                    spectrum = self.spectrum(owner_id, identifier)
                    if spectrum["modality"] != modality:
                        raise ChemistryError("invalid_input", f"{modality}_id refers to a different spectral modality.")
                    if not spectrum["quality"]["model_eligible"]:
                        raise ChemistryError("spectrum_not_eligible", " ".join(spectrum["quality"]["reasons"]), 422)
                    inputs[modality] = spectrum["intensity"]
                elif modality in inputs:
                    try:
                        inputs[modality] = normalize_model_input(inputs[modality]).tolist()
                    except ValueError as error:
                        raise ChemistryError("invalid_input", str(error)) from error
            for label in ("nmr_h", "nmr_c"):
                if label in inputs:
                    with np.errstate(over="ignore", invalid="ignore"):
                        peaks = np.asarray(inputs[label], dtype=np.float32)
                    if not np.isfinite(peaks).all():
                        raise ChemistryError("invalid_input", "NMR shifts must be finite model-representable numbers (ppm).")
                    inputs[label] = np.sort(peaks).tolist()
            inputs.setdefault("limit", 5 if request.operation == "generate" else 8)
        job = self.store.create_job(
            owner_id, request.operation, inputs, source=source,
            request_id=request.request_id, fingerprint=fingerprint, new_molecule=new_molecule,
        )
        # The worker, rather than the HTTP/MCP request, owns execution from here.
        self._wake.set()
        return job

    def job(self, owner_id: str, identifier: str) -> dict:
        job = self.store.get_job(owner_id, identifier)
        if job is None:
            raise ChemistryError("not_found", "Calculation was not found.", 404)
        return job

    def cancel(self, owner_id: str, identifier: str) -> dict:
        return self.store.cancel_job(owner_id, identifier)

    async def wait(self, owner_id: str, identifier: str, timeout: float) -> dict:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            job = self.job(owner_id, identifier)
            remaining = deadline - asyncio.get_running_loop().time()
            if job["status"] in TERMINAL or remaining <= 0:
                return job
            await asyncio.sleep(min(0.05, remaining))

    async def _work(self) -> None:
        while not self._stopping:
            self._wake.clear()
            claimed = self.store.claim_next()
            if claimed is None:
                await self._wake.wait()
                continue
            owner_id, job = claimed
            started = time.monotonic()
            duration_ms = lambda: round((time.monotonic() - started) * 1000)
            try:
                device = await self.device()
                capability = self._capabilities(device)["capabilities"][job["operation"]]
                if not capability["available"]:
                    raise ChemistryError("model_unavailable", capability["detail"])
                self.store.start_execution(owner_id, job["id"])
                result = await asyncio.to_thread(self._calculate, job["operation"], job["inputs"], device)
                if job["operation"] == "predict_spectra":
                    spectra = {
                        modality: spectrum_record(
                            name=f"{job['inputs']['molecule']['formula']} predicted {modality.upper()}",
                            modality=modality, axis=result["wavenumber"], intensity=result[modality],
                            axis_unit="cm^-1", intensity_unit="normalized [0,1]", domain="theoretical",
                            axis_mode="explicit", provenance={
                                **result["provenance"], "source": "prediction",
                                "job_id": job["id"], "molecule_id": result["molecule_id"],
                            },
                        )
                        for modality in ("ir", "raman")
                    }
                else:
                    spectra = None
                self.store.finish_job(owner_id, job["id"], result=result, spectra=spectra, duration_ms=duration_ms())
            except asyncio.CancelledError:
                self.store.finish_job(owner_id, job["id"], duration_ms=duration_ms(), error={"code": "interrupted", "message": "Service stopped while this calculation was running."})
                raise
            except ChemistryError as error:
                self.store.finish_job(owner_id, job["id"], duration_ms=duration_ms(), error=error.payload())
            except Exception as error:
                self.store.finish_job(owner_id, job["id"], duration_ms=duration_ms(), error={"code": "calculation_failed", "message": str(error)[:2000] or type(error).__name__})

    def _calculate(self, operation: str, inputs: dict, device: str) -> dict:
        from openmolspec_ui.inference import ModelUnavailable, OpenMolSpecService

        try:
            if self._service is None:
                self._service = (self._service_factory or OpenMolSpecService)(self.assets, device=device)
            if operation == "predict_spectra":
                from rdkit import Chem
                from openmolspec_ui.chemistry import MoleculeInput

                mol = Chem.MolFromMolBlock(inputs["molecule"]["molblock"], removeHs=False)
                if mol is None:
                    raise ValueError("Persisted molecule conformer cannot be read.")
                result = dict(self._service.predict_spectra(MoleculeInput(mol, "Persisted conformer")))
                result["molecule_id"] = inputs["molecule_id"]
                backend, cached = "equiformer-v3-harmonic", False
                units = {"wavenumber": "cm^-1", "mode_frequencies": "cm^-1", "ir": "normalized [0,1]",
                         "raman": "normalized [0,1]", "nmr_h": "ppm", "nmr_c": "ppm", "coordinates": "angstrom"}
            else:
                spectra = SpectralInput(**{key: np.asarray(inputs[key], dtype=np.float32) if key in inputs else None
                                          for key in ("ir", "raman", "nmr_h", "nmr_c")})
                if operation == "retrieve":
                    candidates = self._service.retrieve(spectra, limit=inputs.get("limit", 8))
                    result = {"candidates": candidates}
                    backends = sorted({item.get("backend", "unknown") for item in candidates})
                    backend, cached = ", ".join(backends) or "reference-retrieval", False
                    units = {"similarity": "dimensionless"}
                elif operation == "predict_gap":
                    result = dict(self._service.predict_gap(spectra))
                    backend, cached = "vib2conf", False
                    units = {"gap_ev": "eV", "benchmark_mae_ev": "eV"}
                else:
                    result = dict(self._service.generate(spectra, limit=inputs.get("limit", 5)))
                    cached = "cache" in result.get("mode", "").lower()
                    backend = "vib2mol-test-set-cache" if cached else "vib2mol-beam-search"
                    units = {"score": "dimensionless ranking score"}
            result["domain"] = "theoretical"
            result["units"] = {**units, **result.get("units", {})}
            result["provenance"] = {
                "backend": backend, "device": device,
                "cache": {"used": cached, "kind": "theoretical-test-set-generation" if cached else None},
                **result.get("provenance", {}),
            }
            if "mode" in result:
                result["provenance"]["mode"] = result["mode"]
            try:
                return json_value(result)
            except ValueError as error:
                raise ChemistryError("invalid_result", str(error)) from error
        except (ModelUnavailable, ModuleNotFoundError, FileNotFoundError) as error:
            raise ChemistryError("model_unavailable", str(error)) from error


def compact_job(job: dict) -> dict:
    """Bound LLM context to scientific summaries, references and provenance."""
    output = {"job_id": job["id"], "operation": job["operation"], "status": job["status"],
              "summary": {}, "error": job["error"], "domain": "theoretical"}
    output["input_refs"] = {key: job["inputs"][key] for key in ("molecule_id", "ir_id", "raman_id")
                            if key in job["inputs"]}
    result = job["result"]
    if result is None:
        return output
    output.update({key: result[key] for key in ("units", "provenance") if key in result})
    summary = output["summary"]
    if job["operation"] == "predict_spectra":
        summary["molecule_id"] = result.get("molecule_id")
        for field in ("ir_id", "raman_id"):
            if field in result:
                output[field] = result[field]
        for modality in ("ir", "raman"):
            values = result.get(modality, [])
            axis = result.get("wavenumber", [])
            summary[modality] = {"points": len(values)}
            if values and len(axis) == len(values):
                summary[modality]["peak_wavenumber_cm1"] = axis[int(np.argmax(values))]
        for label in ("nmr_h", "nmr_c"):
            values = result.get(label, [])
            summary[label] = {"count": len(values), "range_ppm": [min(values), max(values)] if values else None}
    elif job["operation"] == "predict_gap":
        summary.update({key: result[key] for key in ("gap_ev", "benchmark_mae_ev", "benchmark_r2") if key in result})
    else:
        fields = ("smiles", "rank", "sample_id", "similarity", "score", "backend", "source", "matching_probability", "anchor_similarity")
        summary["candidates"] = [
            {key: (item[key][:1000] if isinstance(item[key], str) else item[key]) for key in fields if key in item}
            for item in result.get("candidates", [])[:10]
        ]
        summary["candidate_count"] = len(result.get("candidates", []))
        for key in ("mode", "anchors_used", "anchor_similarity", "beam_size"):
            if key in result:
                summary[key] = result[key]
    return output

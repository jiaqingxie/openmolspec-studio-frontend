"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import {
  predictGap,
  predictSpectra,
  resolveMolecule,
  retrieve,
  generate,
  type GapResponse,
  type GenerateResponse,
  type MoleculeResponse,
  type PredictResponse,
  type RetrieveResponse,
} from "@/lib/api";
import { toolBySlug, TOOLS } from "@/lib/tools";
import { RunBar, useRun } from "@/components/run-bar";
import { MoleculeInput } from "@/components/molecule-input";
import { Molecule3D } from "@/components/molecule-3d";
import { NmrCurve, SpectrumChart } from "@/components/spectrum-chart";
import { SpectrumInput, type ParsedSpectrum } from "@/components/spectrum-input";
import { CandidateList } from "@/components/candidates";
import { CsvButton, StatTable } from "@/components/metric-card";

export default function ToolPage() {
  const router = useRouter();
  const slug = typeof router.query.slug === "string" ? router.query.slug : "";
  const tool = toolBySlug(slug);
  if (!tool) return <p className="text-secondary">unknown tool</p>;

  return (
    <div>
      <nav aria-label="breadcrumb">
        <ol className="breadcrumb mb-2" style={{ fontSize: "0.8rem" }}>
          <li className="breadcrumb-item">
            <Link href="/">Home</Link>
          </li>
          <li className="breadcrumb-item active" aria-current="page">
            {tool.name}
          </li>
        </ol>
      </nav>
      <h1 className="h5 mb-1" style={{ color: "var(--oms-primary)" }}>
        Tool {tool.index} — {tool.name}
      </h1>
      <p className="text-secondary" style={{ maxWidth: "76ch", fontSize: "0.88rem", lineHeight: 1.6 }}>
        {tool.desc}
      </p>
      <p className="font-monospace text-secondary mb-4" style={{ fontSize: "0.78rem" }}>
        {tool.io} · {tool.bench}
      </p>

      {tool.slug === "structure-to-spectrum" && <StructurePage />}
      {tool.slug === "spectrum-retrieval" && <SpectrumToolPage mode="retrieval" />}
      {tool.slug === "spectrum-to-gap" && <SpectrumToolPage mode="gap" />}
      {tool.slug === "spectrum-to-generation" && <SpectrumToolPage mode="generation" />}
    </div>
  );
}

function DemoTag() {
  return (
    <span className="badge text-bg-warning" style={{ fontWeight: 500 }}>
      demo data
    </span>
  );
}

function ResultTabs({ tabs }: { tabs: { label: string; content: React.ReactNode }[] }) {
  const [active, setActive] = useState(0);
  return (
    <div>
      <ul className="nav nav-tabs mb-3">
        {tabs.map((tab, index) => (
          <li className="nav-item" key={tab.label}>
            <button
              type="button"
              className={`nav-link py-1 ${active === index ? "active" : ""}`}
              onClick={() => setActive(index)}
            >
              {tab.label}
            </button>
          </li>
        ))}
      </ul>
      {tabs[active]?.content}
    </div>
  );
}

function StructurePage() {
  const [smiles, setSmiles] = useState("CC(=O)OC1=CC=CC=C1C(=O)O");
  const [molecule, setMolecule] = useState<MoleculeResponse | null>(null);
  const [previewOffline, setPreviewOffline] = useState(false);
  const [result, setResult] = useState<PredictResponse | null>(null);
  const [resultDemo, setResultDemo] = useState(false);
  const { state, run } = useRun();

  useEffect(() => {
    const trimmed = smiles.trim();
    if (!trimmed) {
      setMolecule(null);
      setPreviewOffline(false);
      return;
    }
    const timer = setTimeout(() => {
      resolveMolecule(trimmed)
        .then((response) => {
          setMolecule(response.data);
          setPreviewOffline(false);
        })
        .catch(() => {
          setMolecule(null);
          setPreviewOffline(true);
        });
    }, 400);
    return () => clearTimeout(timer);
  }, [smiles]);

  const predictCsv = useMemo(() => {
    if (!result) return "";
    const lines = ["wavenumber,ir,raman"];
    result.wavenumber.forEach((x, i) => lines.push(`${x},${result.ir[i]},${result.raman[i]}`));
    lines.push("");
    lines.push("1H shift ppm,13C shift ppm");
    const rows = Math.max(result.nmr_h.length, result.nmr_c.length);
    for (let i = 0; i < rows; i += 1) lines.push(`${result.nmr_h[i] ?? ""},${result.nmr_c[i] ?? ""}`);
    return lines.join("\n");
  }, [result]);

  return (
    <div className="vstack gap-3">
      <div className="card">
        <div className="card-header">Input — molecule</div>
        <div className="card-body">
          <MoleculeInput smiles={smiles} onChange={setSmiles} />
        </div>
      </div>

      <div className="card">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span>Conformer preview</span>
          {molecule && (
            <span className="font-monospace text-secondary" style={{ fontSize: "0.75rem", fontWeight: 400 }}>
              {molecule.formula} · {molecule.atoms} atoms · {molecule.source}
            </span>
          )}
        </div>
        <div className="card-body">
          <Molecule3D xyz={molecule ? molecule.xyz : null} formula={molecule?.formula} />
          {previewOffline && (
            <div className="alert alert-warning py-1 px-3 mt-2 mb-0" style={{ fontSize: "0.85rem" }}>
              Backend offline — 3D preview and inference unavailable. Running will show demo data.
            </div>
          )}
        </div>
      </div>

      <RunBar
        label="Run prediction"
        state={state}
        disabled={!smiles.trim()}
        onRun={() =>
          void run(async () => {
            const response = await predictSpectra(smiles.trim());
            setResult(response.data);
            setResultDemo(response.demo);
          })
        }
      />

      {result && (
        <div className="card">
          <div className="card-header d-flex justify-content-between align-items-center">
            <span>Results — predicted spectra</span>
            <span className="d-flex gap-2 align-items-center" style={{ fontWeight: 400 }}>
              {resultDemo && <DemoTag />}
              <CsvButton csv={predictCsv} filename="openmolspec_predicted_spectra.csv" label="Download CSV" />
            </span>
          </div>
          <div className="card-body">
            <ResultTabs
              tabs={[
                {
                  label: "IR",
                  content: (
                    <>
                      <SpectrumChart
                        series={[
                          {
                            name: "IR",
                            color: "#0c5da5",
                            points: result.wavenumber.map((x, i) => ({ x, y: result.ir[i] })),
                          },
                        ]}
                        xLabel="wavenumber (cm⁻¹)"
                      />
                      <p className="figure-caption-text mt-1 mb-0">
                        Predicted theoretical IR spectrum, min–max normalized intensity, 400–4000 cm⁻¹.
                      </p>
                    </>
                  ),
                },
                {
                  label: "Raman",
                  content: (
                    <>
                      <SpectrumChart
                        series={[
                          {
                            name: "Raman",
                            color: "#00a36c",
                            points: result.wavenumber.map((x, i) => ({ x, y: result.raman[i] })),
                          },
                        ]}
                        xLabel="wavenumber (cm⁻¹)"
                      />
                      <p className="figure-caption-text mt-1 mb-0">
                        Predicted theoretical Raman spectrum, min–max normalized intensity.
                      </p>
                    </>
                  ),
                },
                {
                  label: "¹H NMR",
                  content: (
                    <>
                      <NmrCurve peaks={result.nmr_h} nucleus="H" color="#b26a00" />
                      <PeakTable values={result.nmr_h} label="¹H shift (ppm)" />
                    </>
                  ),
                },
                {
                  label: "¹³C NMR",
                  content: (
                    <>
                      <NmrCurve peaks={result.nmr_c} nucleus="C" color="#845b97" />
                      <PeakTable values={result.nmr_c} label="¹³C shift (ppm)" />
                    </>
                  ),
                },
                {
                  label: "Modes",
                  content: (
                    <div className="table-responsive scrollbar-thin" style={{ maxHeight: 320 }}>
                      <table className="table table-sm table-striped mb-0">
                        <thead>
                          <tr>
                            <th>freq (cm⁻¹)</th>
                            <th>IR activity</th>
                            <th>Raman activity</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.modes.map((mode, index) => (
                            <tr key={index}>
                              <td className="font-monospace">{mode.frequency.toFixed(2)}</td>
                              <td className="font-monospace">{mode.ir_activity.toFixed(4)}</td>
                              <td className="font-monospace">{mode.raman_activity.toFixed(4)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ),
                },
              ]}
            />
            <div className="alert alert-light border py-2 px-3 mt-3 mb-0" style={{ fontSize: "0.8rem", lineHeight: 1.55 }}>
              <strong>Methods.</strong> IR/Raman are reconstructed from predicted Hi, Hij, ∂μ/∂R, ∂α/∂R
              via mass-weighted normal modes, 0.965 frequency scaling and Lorentz broadening. NMR
              shifts are atom-level, unassigned, without J-coupling.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface SpectrumQueryState {
  ir: ParsedSpectrum | null;
  raman: ParsedSpectrum | null;
  nmr_h: number[];
  nmr_c: number[];
  ready: boolean;
  demo: boolean;
}

function SpectrumToolPage({ mode }: { mode: "retrieval" | "gap" | "generation" }) {
  const [query, setQuery] = useState<SpectrumQueryState | null>(null);
  const [limit, setLimit] = useState(8);
  const [retrieval, setRetrieval] = useState<RetrieveResponse | null>(null);
  const [gap, setGap] = useState<GapResponse | null>(null);
  const [generation, setGeneration] = useState<GenerateResponse | null>(null);
  const [resultDemo, setResultDemo] = useState(false);
  const { state, run } = useRun();

  const payload = () => ({
    ir: query?.ir ? { wavenumber: query.ir.wavenumber ?? null, intensity: query.ir.intensity } : null,
    raman: query?.raman
      ? { wavenumber: query.raman.wavenumber ?? null, intensity: query.raman.intensity }
      : null,
    nmr_h: query?.nmr_h ?? [],
    nmr_c: query?.nmr_c ?? [],
    limit,
  });

  const onRun = () =>
    void run(async () => {
      if (mode === "retrieval") {
        const response = await retrieve(payload());
        setRetrieval(response.data);
        setResultDemo(response.demo);
      } else if (mode === "gap") {
        const response = await predictGap(payload());
        setGap(response.data);
        setResultDemo(response.demo);
      } else {
        const response = await generate(payload());
        setGeneration(response.data);
        setResultDemo(response.demo);
      }
    });

  return (
    <div className="vstack gap-3">
      <div className="card">
        <div className="card-header">Input — theoretical spectra</div>
        <div className="card-body">
          <SpectrumInput onQuery={setQuery} />
          {mode !== "gap" && (
            <div className="mt-3 d-flex align-items-center gap-2">
              <label className="form-label mb-0" htmlFor="limit-range">
                Number of candidates
              </label>
              <input
                id="limit-range"
                type="range"
                className="form-range"
                style={{ maxWidth: 220 }}
                min={3}
                max={mode === "retrieval" ? 15 : 12}
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value))}
              />
              <span className="font-monospace">{limit}</span>
            </div>
          )}
        </div>
      </div>

      <RunBar
        label={
          mode === "retrieval"
            ? "Run retrieval"
            : mode === "gap"
              ? "Predict HOMO–LUMO gap"
              : "Generate structures"
        }
        state={state}
        disabled={!query?.ready}
        onRun={onRun}
      />

      {mode === "retrieval" && retrieval && (
        <div className="card">
          <div className="card-header d-flex justify-content-between align-items-center">
            <span>Results — ranked candidates</span>
            <span className="d-flex gap-2 align-items-center" style={{ fontWeight: 400 }}>
              {resultDemo && <DemoTag />}
              <span className="font-monospace text-secondary" style={{ fontSize: "0.75rem" }}>
                backend: {retrieval.candidates[0]?.backend ?? "spectral-cosine"}
              </span>
            </span>
          </div>
          <div className="card-body">
            <CandidateList candidates={retrieval.candidates} />
            <p className="figure-caption-text mt-1 mb-0">
              Top-ranked molecules from the 200k test-set library for the submitted multimodal query.
              Score combines cosine similarity over vibrational spectra with H/C peak-set matching.
            </p>
          </div>
        </div>
      )}

      {mode === "gap" && gap && (
        <div className="card">
          <div className="card-header d-flex justify-content-between align-items-center">
            <span>Results — predicted gap</span>
            {resultDemo && (
              <span style={{ fontWeight: 400 }}>
                <DemoTag />
              </span>
            )}
          </div>
          <div className="card-body">
            <StatTable
              rows={[
                {
                  label: "predicted gap",
                  value: `${gap.gap_ev.toFixed(3)} eV`,
                  detail: "current input · HOMO–LUMO",
                },
                {
                  label: "test MAE",
                  value: `${gap.benchmark_mae_ev.toFixed(3)} eV`,
                  detail: "fixed test set · 20,390 molecules",
                },
                {
                  label: "test R²",
                  value: gap.benchmark_r2_ev.toFixed(3),
                  detail: "fixed test set · OpenMolSpec 1M",
                },
              ]}
            />
            <p className="figure-caption-text mt-2 mb-0">
              Predictions are de-normalized to eV. Benchmarks are fixed test-set population
              statistics, not per-sample intervals; inputs must stay inside the trained 400–4000 cm⁻¹
              domain.
            </p>
          </div>
        </div>
      )}

      {mode === "generation" && generation && (
        <div className="card">
          <div className="card-header d-flex justify-content-between align-items-center">
            <span>Results — generated candidates</span>
            {resultDemo && (
              <span style={{ fontWeight: 400 }}>
                <DemoTag />
              </span>
            )}
          </div>
          <div className="card-body">
            <div className="alert alert-light border py-2 px-3" style={{ fontSize: "0.8rem", lineHeight: 1.55 }}>
              {generation.note}
            </div>
            <CandidateList candidates={generation.candidates} scoreLabel="confidence" />
            <p className="figure-caption-text mt-1 mb-0">
              Reference performance on the 200k Vib2Mol test set: reranked top-1 68.13% · top-5
              80.02% · valid SMILES 97.67%.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function PeakTable({ values, label }: { values: number[]; label: string }) {
  return (
    <div className="table-responsive scrollbar-thin" style={{ maxHeight: 220 }}>
      <table className="table table-sm table-striped mb-0">
        <thead>
          <tr>
            <th style={{ width: 48 }}>#</th>
            <th>{label}</th>
          </tr>
        </thead>
        <tbody>
          {values.map((value, index) => (
            <tr key={index}>
              <td className="text-secondary font-monospace">{index + 1}</td>
              <td className="font-monospace">{value.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export async function getStaticPaths() {
  return {
    paths: TOOLS.map((tool) => ({ params: { slug: tool.slug } })),
    fallback: false,
  };
}

export async function getStaticProps() {
  return { props: {} };
}

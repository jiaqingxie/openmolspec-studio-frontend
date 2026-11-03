from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


Operation = Literal["predict_spectra", "retrieve", "predict_gap", "generate"]
Identifier = Annotated[str, Field(min_length=1, max_length=128)]
Smiles = Annotated[str, Field(min_length=1, max_length=20000)]
XYZ = Annotated[str, Field(min_length=1, max_length=10 * 1024 * 1024)]
Number = Annotated[FiniteFloat, Field(strict=True)]
SpectrumArray = Annotated[list[Number], Field(min_length=1024, max_length=1024)]
Peaks = Annotated[list[Number], Field(max_length=4096)]
Limit = Annotated[int, Field(strict=True, ge=1, le=50)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StructureRequest(StrictModel):
    smiles: Smiles | None = None
    xyz: XYZ | None = None

    @model_validator(mode="after")
    def one_structure(self) -> Self:
        supplied = [value for value in (self.smiles, self.xyz) if value is not None]
        if len(supplied) != 1 or not supplied[0].strip():
            raise ValueError("Provide exactly one nonempty SMILES or XYZ structure.")
        return self


class ParseSpectrumRequest(StrictModel):
    content: Annotated[str, Field(min_length=1, max_length=10 * 1024 * 1024)]
    name: Annotated[str, Field(min_length=1, max_length=512)]
    modality: Literal["ir", "raman"] = "ir"
    axis_unit: Literal["cm^-1", "nm", "unknown"] = "unknown"
    intensity_unit: Annotated[str, Field(min_length=1, max_length=48)] = "unknown"
    domain: Literal["theoretical", "experimental", "unknown"] = "unknown"
    axis_mode: Literal["explicit", "model_grid"] = "explicit"


class CalculationInputs(StrictModel):
    molecule_id: Identifier | None = None
    smiles: Smiles | None = None
    xyz: XYZ | None = None
    ir_id: Identifier | None = None
    raman_id: Identifier | None = None
    ir: SpectrumArray | None = None
    raman: SpectrumArray | None = None
    nmr_h: Peaks | None = None
    nmr_c: Peaks | None = None
    limit: Limit | None = None

    @model_validator(mode="after")
    def unambiguous_inputs(self) -> Self:
        if sum(value is not None for value in (self.molecule_id, self.smiles, self.xyz)) > 1:
            raise ValueError("molecule_id, smiles and xyz are alternative structure representations.")
        for modality in ("ir", "raman"):
            if getattr(self, modality) is not None and getattr(self, f"{modality}_id") is not None:
                raise ValueError(f"Provide {modality} or {modality}_id, not both.")
        return self


class JobRequest(StrictModel):
    operation: Operation
    inputs: CalculationInputs
    request_id: Identifier | None = None

    @model_validator(mode="after")
    def operation_inputs(self) -> Self:
        inputs = self.inputs
        structure = any(value is not None for value in (inputs.molecule_id, inputs.smiles, inputs.xyz))
        spectral = any(value is not None for value in (inputs.ir, inputs.raman, inputs.ir_id, inputs.raman_id))
        if self.operation == "predict_spectra":
            if not structure or spectral or inputs.nmr_h is not None or inputs.nmr_c is not None:
                raise ValueError("predict_spectra requires one structure and accepts no spectral input.")
        elif structure or not spectral:
            raise ValueError("This operation requires IR or Raman input and accepts no structure.")
        return self

"""Authoritative machine-readable field definitions for OpenSpec v1.

The schema describes the public record contract. It does not yet convert the
legacy parser output; that is intentionally deferred to the parser-reliability
phase. Every field carries a dtype, shape, unit, missing-value policy and
description so release builders and validators can consume one definition.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from .constants import (
    CALCULATION_METADATA_FIELDS,
    PARSER_VERSION,
    PROCESSING_VERSION,
    SCHEMA_VERSION as _SCHEMA_VERSION,
    SPECTRUM_PARAMETERS,
)


@dataclass(frozen=True)
class FieldSpec:
    """Specification for one OpenSpec record field."""

    dtype: str
    shape: str
    unit: Optional[str]
    missing_value_policy: str
    description: str
    required: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _field(
    dtype: str,
    shape: str,
    unit: Optional[str],
    missing_value_policy: str,
    description: str,
    *,
    required: bool = False,
) -> FieldSpec:
    return FieldSpec(
        dtype=dtype,
        shape=shape,
        unit=unit,
        missing_value_policy=missing_value_policy,
        description=description,
        required=required,
    )


SCHEMA_VERSION = _SCHEMA_VERSION

OPEN_SPEC_V1_SCHEMA: Mapping[str, FieldSpec] = {
    "sample_id": _field(
        "string", "scalar", None, "must be present", "Globally unique sample identifier.", required=True
    ),
    "source_dataset": _field(
        "string", "scalar", None, "must be present", "Name of the original source dataset.", required=True
    ),
    "source_id": _field(
        "string", "scalar", None, "must be present", "Identifier in the original source dataset.", required=True
    ),
    "smiles": _field("string", "scalar", None, "null and list in missing_fields", "Input or source SMILES."),
    "canonical_smiles": _field(
        "string", "scalar", None, "null and list in missing_fields", "Standardized canonical SMILES."
    ),
    "inchikey": _field(
        "string", "scalar", None, "null and list in missing_fields", "InChIKey used for molecular identity."
    ),
    "atomic_numbers": _field(
        "int32", "N", None, "null and list in missing_fields", "Atomic number for each atom.", required=True
    ),
    "coordinates": _field(
        "float32", "N x 3", "angstrom", "null and list in missing_fields", "Optimized Cartesian coordinates."
    ),
    "energy": _field("float64", "scalar or source-defined", "source-defined", "null and flag", "Electronic energy."),
    "zpve": _field("float64", "scalar or source-defined", "source-defined", "null and flag", "Zero-point vibrational energy."),
    "U0": _field("float64", "scalar or source-defined", "source-defined", "null and flag", "Energy plus zero-point vibrational energy."),
    "U": _field("float64", "scalar or source-defined", "source-defined", "null and flag", "Internal energy from the source calculation."),
    "H": _field("float64", "scalar or source-defined", "source-defined", "null and flag", "Enthalpy from the source calculation."),
    "G": _field("float64", "scalar or source-defined", "source-defined", "null and flag", "Gibbs free energy from the source calculation."),
    "dipole": _field("float64", "source-defined", "source-defined", "null and flag", "Dipole-related archive quantity."),
    "polarizability": _field("float64", "3 x 3", "source-defined", "null and flag", "Polarizability tensor."),
    "homo": _field("float64", "scalar", "source-defined", "null and flag", "Highest occupied molecular orbital energy."),
    "lumo": _field("float64", "scalar", "source-defined", "null and flag", "Lowest unoccupied molecular orbital energy."),
    "gap": _field("float64", "scalar", "source-defined", "null and flag", "LUMO minus HOMO."),
    "hessian": _field("float32", "3N x 3N", "source-defined", "null and flag", "Cartesian Hessian matrix."),
    "frequencies": _field("float64", "variable", "cm^-1", "null and flag", "Vibrational frequencies after documented scaling."),
    "ir_intensities": _field("float64", "variable", "source-defined", "null and flag", "Raw IR intensities aligned with frequencies."),
    "ir_spectrum": _field("float64", "fixed grid", "source-defined", "null and flag", "Broadened IR spectrum."),
    "raman_activities": _field("float64", "variable", "source-defined", "null and flag", "Raw Raman activities aligned with frequencies."),
    "raman_spectrum": _field("float64", "fixed grid", "documented intensity", "null and flag", "Broadened Raman intensity spectrum."),
    "nmr_isotropic": _field("float64", "variable", "documented NMR unit", "null and flag", "Per-atom isotropic NMR shielding or shift."),
    "nmr_anisotropy": _field("float64", "variable", "documented NMR unit", "null and flag", "Per-atom NMR anisotropy."),
    "nmr_tensor": _field("float64", "N x 3 x 3", "documented NMR unit", "null and flag", "Per-atom NMR shielding tensor."),
    "nmr_shifts": _field("float64", "variable or fixed grid", "ppm or documented", "null and flag", "NMR chemical shifts or processed NMR spectrum."),
    "source_file_hash": _field("string", "scalar", "SHA-256", "must be present when source is available", "Hash of the source file."),
    "frequency_file_hash": _field(
        "string", "scalar", "SHA-256", "null when frequency source is unavailable",
        "Hash of the Gaussian frequency/property source log.",
    ),
    "nmr_file_hash": _field(
        "string", "scalar", "SHA-256", "null when NMR source is unavailable",
        "Hash of the Gaussian NMR source log.",
    ),
    "parser_version": _field("string", "scalar", None, "must be present", "Version of the parser producing the record.", required=True),
    "processing_version": _field("string", "scalar", None, "must be present", "Version of the processing convention.", required=True),
    "quality_flags": _field("list[string]", "variable", None, "empty list if none", "Non-destructive validation and provenance flags."),
    "missing_fields": _field("list[string]", "variable", None, "empty list if none", "Fields unavailable for this record."),
}


REQUIRED_FIELDS: Tuple[str, ...] = tuple(
    name for name, spec in OPEN_SPEC_V1_SCHEMA.items() if spec.required
)


SCHEMA_METADATA: Mapping[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "parser_version": PARSER_VERSION,
    "processing_version": PROCESSING_VERSION,
    "calculation_metadata_fields": CALCULATION_METADATA_FIELDS,
    "spectrum_parameters": dict(SPECTRUM_PARAMETERS),
    "field_count": len(OPEN_SPEC_V1_SCHEMA),
}


def schema_as_dict() -> Dict[str, Any]:
    """Return a JSON/YAML-serializable schema representation."""

    return {
        "schema": dict(SCHEMA_METADATA),
        "fields": {name: spec.as_dict() for name, spec in OPEN_SPEC_V1_SCHEMA.items()},
    }


def validate_record_keys(record: Mapping[str, Any]) -> Tuple[str, ...]:
    """Return missing required keys without validating numerical values yet."""

    return tuple(name for name in REQUIRED_FIELDS if name not in record)

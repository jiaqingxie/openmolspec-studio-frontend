"""Shared physical constants and frozen OpenSpec v1 processing parameters.

These definitions are metadata for the v1 release. Existing extraction scripts
are intentionally not changed by this module yet; parser integration is a
later phase of the execution plan.
"""

from types import MappingProxyType

# SI constants used by the current Raman-intensity implementation.
CM_TO_HZ = 2.99792458e10
ANGSTROM_TO_METER = 1.0e-10
BOLTZMANN_CONSTANT = 1.380649e-23
PLANCK_CONSTANT = 6.62606896e-34
SPEED_OF_LIGHT = 299792458.0
HARTREE_TO_EV = 27.211386245988
BOHR_TO_ANGSTROM = 0.529177210903
HESSIAN_AU_TO_EV_ANGSTROM2 = HARTREE_TO_EV / BOHR_TO_ANGSTROM**2

SCHEMA_VERSION = "1.0"
PARSER_VERSION = "0.1.0"
PROCESSING_VERSION = "1.0.0"

# These values reflect the currently documented production convention. They
# are exposed explicitly so a future parser can select or revise them through
# configuration rather than duplicating literals in multiple scripts.
SPECTRUM_PARAMETERS = MappingProxyType(
    {
        "frequency_min_cm-1": 400.0,
        "frequency_max_cm-1": 4000.0,
        "frequency_grid_size": 1024,
        "frequency_scaling_factor": 0.965,
        "line_shape": "lorentzian",
        # DetaNet example convention: IR FWHM-like sigma=20; keep the
        # OpenSpec grid independently fixed at 400-4000 cm^-1 / 1024 points.
        "ir_broadening_sigma_cm-1": 20.0,
        "raman_broadening_sigma_cm-1": 12.0,
        "raman_temperature_K": 298.0,
        "raman_excitation_wavelength_nm": 532.0,
        "nmr_frequency_min": 0.0,
        "nmr_frequency_max": 12.0,
        "nmr_grid_size": 1024,
        "nmr_broadening_sigma": 0.05,
    }
)

CALCULATION_METADATA_FIELDS = (
    "gaussian_version",
    "functional",
    "basis_set",
    "charge",
    "multiplicity",
)

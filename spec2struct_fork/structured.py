"""Parse experimental NMR prose into one feature token per chemical shift."""

from __future__ import annotations

import re

import torch
from torch.nn.utils.rnn import pad_sequence


# Feature layout is shared by the parser and StructuredSourceEmbedding.
KIND, SHIFT, WIDTH, SHIFT_PRESENT, MULTIPLICITY = range(5)
INTEGRATION, INTEGRATION_PRESENT, J1, J2, J3, J_COUNT = range(5, 11)
FREQUENCY, FREQUENCY_PRESENT, SUBTYPE, ELEMENT, ELEMENT_COUNT, SOLVENT = range(11, 17)
FEATURE_COUNT = 17
PAD_KIND, CLS_KIND, FORMULA_KIND, H_KIND, C_KIND = range(5)

ELEMENTS = ("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe "
            "Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn "
            "Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W "
            "Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf "
            "Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og").split()
ELEMENT_IDS = {symbol: index + 1 for index, symbol in enumerate(ELEMENTS)}
MULTIPLICITIES = ("unknown s d t q m br_s br_d br_t br_m dd dt dq td tt ddd ddt "
                  "dddd quint sext sept other").split()
MULTIPLICITY_IDS = {name: index for index, name in enumerate(MULTIPLICITIES)}
SOLVENTS = ("unknown cdcl3 dmso d2o cd3od acetone benzene acetonitrile thf "
            "chloroform dichloromethane toluene").split()
SOLVENT_IDS = {name: index for index, name in enumerate(SOLVENTS)}

_SHIFT = re.compile(
    r"(?<![\w.])(?P<first>[+-]?\d{1,3}(?:\.\d+)?)"
    r"(?:\s*[-–—]\s*(?P<second>[+-]?\d{1,3}(?:\.\d+)?))?(?![\w.])")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_INTEGRATION = re.compile(r"(?<![A-Za-z0-9])(?P<count>\d+(?:\.\d+)?)\s*H\b", re.I)
_J = re.compile(r"\bJ\s*=?\s*(\d+(?:\.\d+)?(?:\s*(?:,|and)\s*\d+(?:\.\d+)?)*)", re.I)
_FREQUENCY = re.compile(r"(\d+(?:\.\d+)?)\s*MHz", re.I)
_MULT = re.compile(
    r"\b(dddd|ddt|ddd|dd|dt|dq|td|tt|qd|quintet|quint|quin|sextet|sext|"
    r"septet|sept|multiplet|singlet|doublet|triplet|quartet|broad|br|bs|bd|bt|"
    r"m|s|d|t|q)\b", re.I)
_FORMULA = re.compile(r"([A-Z][a-z]?)(\d*)")


def _split_outside_parentheses(text: str) -> list[str]:
    chunks, start, depth = [], 0, 0
    for index, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char in ",;" and depth == 0:
            chunks.append(text[start:index])
            start = index + 1
    chunks.append(text[start:])
    return chunks


def _multiplicity(annotation: str) -> int:
    names = [match.group(1).lower() for match in _MULT.finditer(annotation)]
    if not names:
        return 0
    aliases = {"singlet": "s", "doublet": "d", "triplet": "t", "quartet": "q",
               "multiplet": "m", "quintet": "quint", "quin": "quint",
               "sextet": "sext", "septet": "sept", "broad": "br", "bs": "br_s",
               "bd": "br_d", "bt": "br_t", "qd": "dq"}
    names = [aliases.get(name, name) for name in names]
    if names[0] == "br" and len(names) > 1:
        return MULTIPLICITY_IDS.get("br_" + names[1], MULTIPLICITY_IDS["br_m"])
    if names[0] == "br":
        return MULTIPLICITY_IDS["br_m"]
    return MULTIPLICITY_IDS.get(names[0], MULTIPLICITY_IDS["other"])


def _solvent_id(value: object) -> int:
    text = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
    if "dmso" in text:
        return SOLVENT_IDS["dmso"]
    if "cdcl3" in text:
        return SOLVENT_IDS["cdcl3"]
    if "d2o" in text:
        return SOLVENT_IDS["d2o"]
    if "cd3od" in text or "methanol" in text:
        return SOLVENT_IDS["cd3od"]
    for name in SOLVENTS[5:]:
        if name in text:
            return SOLVENT_IDS[name]
    return 0


def parse_nmr_record(record: dict, nucleus: str) -> list[list[float]]:
    """Parse peaks; unparseable records retain one token with shift_present=0."""
    text = str(record.get("chemical_shift") or "")
    frequency_match = _FREQUENCY.search(str(record.get("frequency") or ""))
    frequency = float(frequency_match.group(1)) if frequency_match else 0.0
    subtype = 1 if "DEPT" in str(record.get("type") or "").upper() else 0
    solvent = _solvent_id(record.get("solvent"))
    kind = H_KIND if nucleus == "h" else C_KIND
    # Organometallic and paramagnetic compounds can have shifts far outside
    # the conventional organic-molecule windows.
    lower, upper = (-100.0, 250.0) if nucleus == "h" else (-250.0, 600.0)
    peaks = []
    for chunk in _split_outside_parentheses(text):
        annotation = " ".join(re.findall(r"[({]([^)}]*)[)}]", chunk))
        outside = re.sub(r"[({][^)}]*[)}]", " ", chunk)
        integration = _INTEGRATION.search(annotation)
        j_values = [float(number) for match in _J.finditer(annotation)
                    for number in _NUMBER.findall(match.group(1))][:3]
        mult = _multiplicity(annotation)
        for match in _SHIFT.finditer(outside):
            first = float(match.group("first"))
            second = float(match.group("second")) if match.group("second") else first
            center = (first + second) / 2
            if not lower <= center <= upper:
                continue
            row = [0.0] * FEATURE_COUNT
            row[KIND], row[SHIFT], row[WIDTH], row[SHIFT_PRESENT] = kind, center, abs(first - second), 1
            row[MULTIPLICITY] = mult
            if integration:
                row[INTEGRATION] = float(integration.group("count"))
                row[INTEGRATION_PRESENT] = 1
            for index, value in enumerate(j_values):
                row[J1 + index] = value
            row[J_COUNT] = len(j_values)
            row[FREQUENCY], row[FREQUENCY_PRESENT] = frequency, int(bool(frequency_match))
            row[SUBTYPE], row[SOLVENT] = subtype, solvent
            peaks.append(row)
    if not peaks:
        row = [0.0] * FEATURE_COUNT
        row[KIND], row[FREQUENCY], row[FREQUENCY_PRESENT] = kind, frequency, int(bool(frequency_match))
        row[SUBTYPE], row[SOLVENT] = subtype, solvent
        peaks.append(row)
    return peaks


def encode_structured_source(formula: str, h_records: list[dict], c_records: list[dict],
                             modality_mask: list[int], limit: int,
                             include_formula: bool = True) -> list[list[float]]:
    if len(modality_mask) != 2 or any(value not in (0, 1) for value in modality_mask):
        raise ValueError("modality_mask must be [has_h, has_c]")
    if not any(modality_mask):
        raise ValueError("At least one NMR modality must be visible")
    if (modality_mask[0] and not h_records) or (modality_mask[1] and not c_records):
        raise ValueError("A visible NMR modality has no records")
    if include_formula and not formula:
        raise ValueError("Molecular formula is required")
    cls = [0.0] * FEATURE_COUNT
    cls[KIND] = CLS_KIND
    result = [cls]
    if include_formula:
        for match in _FORMULA.finditer(formula):
            row = [0.0] * FEATURE_COUNT
            row[KIND] = FORMULA_KIND
            row[ELEMENT] = ELEMENT_IDS.get(match.group(1), 0)
            row[ELEMENT_COUNT] = float(match.group(2) or 1)
            result.append(row)
    for visible, records, nucleus in zip(modality_mask, (h_records, c_records), ("h", "c")):
        if visible:
            for record in records:
                result.extend(parse_nmr_record(record, nucleus))
    if limit < 2:
        raise ValueError("Structured source limit must allow CLS and one peak")
    if len(result) > limit:
        prefix = 1 + len(_FORMULA.findall(formula)) if include_formula else 1
        if prefix >= limit:
            raise ValueError("Structured source limit is too short for the formula")
        peaks = result[prefix:]
        if modality_mask == [1, 1]:
            h = [row for row in peaks if row[KIND] == H_KIND]
            c = [row for row in peaks if row[KIND] == C_KIND]
            budget = limit - prefix
            h_quota = min(len(h), budget // 2)
            c_quota = min(len(c), budget - h_quota)
            h_quota = min(len(h), budget - c_quota)
            result = result[:prefix] + h[:h_quota] + c[:c_quota]
        else:
            result = result[:limit]
    return result


def collate_structured_sources(sources: list[list[list[float]]]) -> torch.Tensor:
    return pad_sequence([torch.tensor(source, dtype=torch.float32) for source in sources],
                        batch_first=True, padding_value=0)

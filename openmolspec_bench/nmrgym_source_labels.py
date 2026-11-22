"""Recover proton references from labelled literature or assigned spectra before fitting."""

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import io
import math
import re
import unicodedata
import zipfile

from rdkit import Chem

# Only complete shift lists are accepted. An unrecognised fragment makes the
# entire spectrum ineligible for automatic substitution.
NUMBER = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
ISOTOPE = r"\d{1,3}\s*[A-Z][a-z]?"
JOINT = re.compile(rf"\b{ISOTOPE}\s*(?:and|/|&)\s*{ISOTOPE}\s*[- ]*NMR\b", re.I)
HEAD = re.compile(
    rf"(?<![\w])(?:\^\s*)?({ISOTOPE})\s*(?:\{{[^{{}}]*\}}\s*)?[- ]*NMR\b",
    re.I,
)
PREFIX = re.compile(
    r"\s*(?:\([^()]*\)\s*)*[:;,=\s]*(?:δ\s*(?:[HC](?!\w))?\s*[:=]?\s*)?(?:\(ppm\)\s*[:=]?\s*)?",
    re.I,
)
SIGNAL = re.compile(
    rf"({NUMBER})(?:\s*[-–—]\s*({NUMBER}))?(?:\s*ppm\b)?(?:\s*\(([^()]*)\))?", re.I
)
SEPARATOR = re.compile(r"\s*[,;]\s*|\s+")
COUPLING = re.compile(
    rf"(?<![A-Za-z])(?:\d+\s*)?J(?:[_\-]?[A-Za-z]{{1,4}})?\s*=\s*({NUMBER}(?:(?:\s*Hz)?\s*(?:,|and)\s*{NUMBER})*)\s*Hz\b",
    re.I,
)
SEP_END = re.compile(r"[\s.;,]*\Z")


@dataclass(frozen=True)
class Signal:
    bounds: tuple
    coupling_hz: tuple

    @property
    def center(self):
        return sum(self.bounds) / len(self.bounds)


def parse_report(text, nucleus):
    """Return ordered signals for one explicit nucleus, or None for ambiguous prose."""
    text = unicodedata.normalize("NFKC", text).replace("−", "-")
    if JOINT.search(text):
        return None
    matches = list(HEAD.finditer(text))
    which = [
        i
        for i, m in enumerate(matches)
        if re.sub(r"\s", "", m[1]).upper() == nucleus.upper()
    ]
    if len(which) != 1:
        return None
    i = which[0]
    body = text[
        matches[i].end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)
    ].strip()
    pos = PREFIX.match(body).end()
    signals = []
    while pos < len(body) and not SEP_END.fullmatch(body[pos:]):
        m = SIGNAL.match(body, pos)
        if not m:
            return None
        bounds = tuple(float(x) for x in m.groups()[:2] if x is not None)
        annotation = m[3] or ""
        js = tuple(
            float(x)
            for group in COUPLING.finditer(annotation)
            for x in re.findall(NUMBER, group[1])
        )
        signals.append(Signal(bounds, js))
        pos = m.end()
        if pos == len(body) or SEP_END.fullmatch(body[pos:]):
            break
        sep = SEPARATOR.match(body, pos)
        if not sep:
            return None
        pos = sep.end()
    return signals or None


def signature(values):
    # The local NMRGym JSON view stores six significant digits.
    return tuple(sorted(float(format(x, "g")) for x in values))


def literature_proposal(h, c, h_text, c_text):
    hs = parse_report(h_text, "1H")
    cs = parse_report(c_text, "13C")
    if not hs or not cs or not c or signature(s.center for s in cs) != signature(c):
        return None
    centers = [s.center for s in hs]
    if not all(math.isfinite(x) for x in centers):
        return None
    original = signature(h)
    if signature(centers) == original:
        return "source_agrees", h
    ends = [x for s in hs for x in s.bounds]
    couplings = [x for s in hs for x in s.coupling_hz]
    if original == signature(c) and len(set(c)) >= 2:
        return "copied_carbon_list", centers
    if original == signature(ends):
        return "range_endpoints", centers
    if couplings and original in (
        signature(ends + couplings),
        signature(centers + couplings),
    ):
        return "coupling_in_shift_list", centers
    return None


def collect_literature(bank, rows, candidates):
    with zipfile.ZipFile(bank) as z:
        names = [name for name in z.namelist() if name.endswith(".csv")]
        if len(names) != 1:
            raise ValueError("Expected one NMRBank CSV")
        with z.open(names[0]) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))
            for i, r in enumerate(reader):
                if r["Retracted"].strip().lower() != "no":
                    continue
                key = r["Standardized SMILES"]
                if key not in rows:
                    key = r["SMILES"]
                if key not in rows:
                    continue
                h, c = rows[key]
                proposal = literature_proposal(
                    h, c, r["1H NMR text"], r["13C NMR text"]
                )
                if proposal:
                    candidates[key].append(
                        (
                            *proposal,
                            dict(
                                dataset="NMRBank",
                                pmcid=r["PMC accession number (PMCID)"],
                                csv_index=i,
                            ),
                        )
                    )


def assigned_proposal(h, c, props):
    sets = {"1H": [], "13C": []}
    predicted = set()
    for field, v in props.items():
        if field in ("Program", "NMRProgram", "NMRMethod", "GeomMethod", "NMRBasisSet"):
            predicted.update(re.findall(r"(?:^|\s)(\d+):", v))
    for field, v in props.items():
        m = re.fullmatch(r"Spectrum (1H|13C) (\d+)", field)
        if m and m[2] not in predicted:
            items = [float(s.split(";")[0]) for s in v.split("|") if s.strip()]
            if items and all(math.isfinite(x) for x in items):
                sets[m[1]].append(items)
    if not c or not h:
        return None
    hc, cc = Counter(signature(h)), Counter(signature(c))
    carbon = [Counter(signature(vals)) for vals in sets["13C"]]
    if not sets["1H"]:
        if any(
            not ((hc + cc) - carbons) or (hc == cc and not (hc - carbons))
            for carbons in carbon
        ):
            return "carbon_only_record", []
        return None
    choices = {}
    for sh in sets["1H"]:
        sc = Counter(signature(sh))
        if sc == hc:
            if any(not (cc - carbons) for carbons in carbon):
                choices[signature(sh)] = ("source_agrees", h)
            continue
        extra = hc - sc
        if not any(abs(x) > 25 for x in extra):
            continue
        if any(not (cc - carbons) and not (extra - carbons) for carbons in carbon):
            choices[signature(sh)] = ("assigned_carbon_in_proton_list", sh)
    if len(choices) == 1:
        return next(iter(choices.values()))
    return ("conflicting_source_spectra", None) if choices else None


def collect_assigned(sdf, rows, candidates):
    targets = defaultdict(list)
    for smi, (h, _) in rows.items():
        if not h or max(map(abs, h)) <= 25:
            continue
        mol = Chem.MolFromSmiles(smi)
        if mol is not None:
            targets[Chem.MolToInchiKey(mol)].append(smi)
    for block in sdf.read_bytes().split(b"$$$$"):
        match = re.search(rb">\s*<INChI key>\s*([A-Z]{14}-[A-Z]{10}-[A-Z])", block)
        if not match or (key := match[1].decode()) not in targets:
            continue
        props = dict(
            re.findall(
                r">\s*<([^>]+)>\n([^\n]+)", block.decode("latin1").replace("\r", "")
            )
        )
        for smi in targets[key]:
            proposal = assigned_proposal(*rows[smi], props)
            if proposal:
                candidates[smi].append(
                    (
                        *proposal,
                        dict(
                            dataset="nmrshiftdb2",
                            id=props["nmrshiftdb2 ID"],
                            inchikey=key,
                        ),
                    )
                )


def source_decisions(rows, bank, sdf):
    candidates = defaultdict(list)
    collect_literature(bank, rows, candidates)
    collect_assigned(sdf, rows, candidates)
    decisions = {}
    for smi, votes in candidates.items():
        answers = {signature(new) if new is not None else None for _, new, _ in votes}
        if len(answers) > 1 or None in answers:
            reason, new = "conflicting_source_spectra", None
        else:
            reason, new, _ = votes[0]
        if reason != "source_agrees":
            decisions[smi] = dict(
                reason=reason, replacement=new, sources=[v[2] for v in votes]
            )
    return decisions

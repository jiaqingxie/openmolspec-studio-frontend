"""Regenerate the homepage's sucrose figure from the BMRB deposit (NumPy, contourpy)."""

import argparse
import json
import re
from pathlib import Path
from urllib.request import urlopen

import contourpy
import numpy as np

ENTRY = "bmse000119"
BASE = f"https://bmrb.io/ftp/pub/bmrb/metabolomics/entry_directories/{ENTRY}"
OUTPUT = Path(__file__).resolve().parents[1] / "website/assets/specimen/sucrose.json"
H_WINDOW = [5.65, 3.25]
C_WINDOW = [110, 58]


def read_source(cache, remote, filename):
    path = cache / filename
    if not path.exists():
        with urlopen(f"{BASE}/{remote}", timeout=150) as response:
            path.write_bytes(response.read())
    return path


def read_pdata(cache, experiment, name):
    return read_source(cache, f"nmr/set01/{experiment}/pdata/1/{name}", f"{experiment}_{name}")


def ppm_axis(cache, experiment, procs):
    text = read_pdata(cache, experiment, procs).read_text()
    fields = dict(re.findall(r"^##\$(\w+)=\s*([^\n]+)", text, re.M))
    assert int(fields["BYTORDP"]) == 0 and int(fields["DTYPP"]) == 0
    size = int(fields["SI"])
    step = float(fields["SW_p"]) / float(fields["SF"]) / size
    return float(fields["OFFSET"]) - step * np.arange(size)


def window(axis, limits):
    return (axis <= limits[0]) & (axis >= limits[1])


def trace(cache, folder, limits):
    axis = ppm_axis(cache, folder, "procs")
    values = np.fromfile(read_pdata(cache, folder, "1r"), dtype="<i4")
    assert len(axis) == len(values)
    selected = window(axis, limits)
    x, y = axis[selected], values[selected]
    y = y / y.max()
    points = []
    # Retain both extrema and their acquisition order in every horizontal bin.
    for group in np.array_split(np.arange(len(x)), min(len(x), 900)):
        for i in sorted({group[np.argmin(y[group])], group[np.argmax(y[group])]}):
            points.append([round(float(x[i]), 4), round(float(y[i]), 4)])
    return points


def hsqc(cache, pairs):
    h, c = ppm_axis(cache, 6, "procs"), ppm_axis(cache, 6, "proc2s")
    mat = np.fromfile(read_pdata(cache, 6, "2rr"), dtype="<i4")
    # In this deposit XDIM in the directly detected (H) dimension equals SI,
    # so each Bruker submatrix contains complete rows.
    assert len(h) == 1024 and "##$XDIM= 1024" in read_pdata(cache, 6, "procs").read_text()
    mat = mat.reshape(len(c), len(h))
    for carbon, proton in pairs:
        local = mat[np.ix_(abs(c - carbon) < .45, abs(h - proton) < .028)]
        assert local.size and local.max() > .08 * mat.max(), (carbon, proton)
    hi, ci = window(h, H_WINDOW), window(c, C_WINDOW)
    z = mat[np.ix_(ci, hi)]
    cg = contourpy.contour_generator(x=h[hi], y=c[ci], z=z / z.max())
    return [
        {"fraction": f, "lines": [line.round(4).tolist() for line in cg.lines(f)]}
        for f in [.085, .19, .37, .65]
    ]


def listed_peaks(star, name):
    frame = star.split(f"save_spectral_peak_{name}\n", 1)[1].split("\nsave_\n", 1)[0]
    rows = re.search(r"_Peak_char.Spectral_peak_list_ID\n(.*?)\bstop_", frame, re.S)[1]
    by_id = {}
    for row in rows.strip().splitlines():
        peak_id, dim, shift = row.split()[:3]
        by_id.setdefault(int(peak_id), {})[int(dim)] = float(shift)
    return list(by_id.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True, help="Directory for the original BMRB files")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    star = read_source(args.cache, f"{ENTRY}.str", f"{ENTRY}.str").read_text()
    mol = read_source(args.cache, f"{ENTRY}.mol", f"{ENTRY}.mol").read_text().splitlines()
    atom_count, bond_count = map(int, mol[3].split()[:2])
    atoms = [[row[31:34].strip(), *map(float, row[:30].split())] for row in mol[4:4 + atom_count]]
    bonds = [[int(row[:3]) - 1, int(row[3:6]) - 1] for row in mol[4 + atom_count:4 + atom_count + bond_count]]
    assert (len(atoms), len(bonds)) == (45, 46)
    pairs = [[v[2], v[1]] for v in listed_peaks(star, "HSQC")]
    assert len(pairs) == 11
    data = {
        "name": "Sucrose", "entry": ENTRY, "source": f"https://bmrb.io/metabolomics/mol_summary/show_data.php?id={ENTRY}",
        "doi": "10.13018/BMSE000119", "depositors": "Madison Metabolomics Consortium (F. Jofre, M. E. Anderson, J. L. Markley)",
        "smiles": re.search(r"^\s*isomeric\s+(\S+)\s+bmse000119", star, re.M)[1],
        "solvent": "D2O", "sample": {"concentration_mM": 100, "temperature_K": 298, "pH": 7.4, "reference": "DSS"},
        "geometryFile": f"{BASE}/{ENTRY}.mol", "atoms": atoms, "bonds": bonds,
        "hsqcPairs": pairs, "protonPeaks": [v[1] for v in listed_peaks(star, "1H")],
        "carbonPeaks": [v[1] for v in listed_peaks(star, "13C")],
        "experiments": {"proton": 2, "carbon": 4, "hsqc": 7}, "hWindow": H_WINDOW, "cWindow": C_WINDOW,
        "protonTrace": trace(args.cache, 1, H_WINDOW), "carbonTrace": trace(args.cache, 3, C_WINDOW),
        "contours": hsqc(args.cache, pairs),
    }
    OUTPUT.write_text(json.dumps(data, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()

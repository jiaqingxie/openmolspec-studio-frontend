import { test } from "node:test";
import assert from "node:assert/strict";
import { selectWorkbenchContext, removeContextField } from "../lib/context.ts";

test("selected structure and spectrum labels stay bound to their selected IDs after workspace edits", () => {
  const molecule = {
    id: "ethanol-conformer-1",
    smiles: "CCO",
    formula: "C2H6O",
  };
  const ir = { id: "ir-original", name: "original-ir.csv" };
  const selection = selectWorkbenchContext({
    molecule,
    draftSmiles: "CCO",
    spectra: { ir },
    nmrH: "",
    nmrC: "",
  });
  molecule.id = "ethylamine-conformer-2";
  molecule.smiles = "CCN";
  molecule.formula = "C2H7N";
  ir.id = "ir-replacement";
  ir.name = "replacement-ir.csv";
  assert.deepEqual(selection.references, {
    molecule_id: "ethanol-conformer-1",
    ir_id: "ir-original",
  });
  assert.equal(selection.labels.molecule_id, "分子 · C2H6O");
  assert.equal(selection.labels.ir_id, "IR · original-ir.csv");
});

test("copying workbench context rejects an unresolved SMILES edit", () => {
  assert.throws(
    () =>
      selectWorkbenchContext({
        molecule: { id: "m1", smiles: "CCO", formula: "C2H6O" },
        draftSmiles: "CCN",
        spectra: {},
        nmrH: "",
        nmrC: "",
      }),
    /结构已修改.*重新解析/,
  );
});

test("workbench context preserves validated NMR peaks even with no molecule or vibrational input selected", () => {
  const selection = selectWorkbenchContext({
    molecule: null,
    draftSmiles: "",
    spectra: {},
    nmrH: "1.2, 2.3; 4",
    nmrC: "18.2 60.4",
  });
  assert.deepEqual(selection.references, {
    nmr_h: [1.2, 2.3, 4],
    nmr_c: [18.2, 60.4],
  });
  assert.equal(selection.labels.nmr_h, "¹H NMR · 3 个峰");
  assert.equal(selection.labels.nmr_c, "¹³C NMR · 2 个峰");
  assert.throws(
    () =>
      selectWorkbenchContext({
        molecule: null,
        draftSmiles: "",
        spectra: {},
        nmrH: "1 NaN",
        nmrC: "",
      }),
    /有限数值/,
  );
});

test("removing a selected field drops its ID and label together without changing the original selection", () => {
  const selection = selectWorkbenchContext({
    molecule: { id: "m1", smiles: "CCO", formula: "C2H6O" },
    draftSmiles: "CCO",
    spectra: {},
    nmrH: "1.2",
    nmrC: "",
  });
  const changed = removeContextField(selection, "molecule_id");
  assert.deepEqual(changed.references, { nmr_h: [1.2] });
  assert.deepEqual(changed.labels, { nmr_h: "¹H NMR · 1 个峰" });
  assert.equal(selection.references.molecule_id, "m1");
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { buildJobInputs, parseShifts, resultSpectra } from "../lib/science.ts";

test("a prediction binds the resolved molecule ID, never the edited SMILES", () => {
  assert.deepEqual(
    buildJobInputs("predict_spectra", {
      moleculeId: "m1",
      irId: "i1",
      nmrH: "",
      nmrC: "",
      limit: 5,
    }),
    { molecule_id: "m1" },
  );
  assert.throws(
    () => buildJobInputs("predict_spectra", { nmrH: "", nmrC: "", limit: 5 }),
    /分子/,
  );
});
test("spectral calculations accept IDs and finite NMR shifts and require a vibrational spectrum", () => {
  assert.deepEqual(
    buildJobInputs("retrieve", {
      irId: "i1",
      nmrH: "1.2, 2.3; 4",
      nmrC: "",
      limit: 5,
    }),
    { ir_id: "i1", nmr_h: [1.2, 2.3, 4], limit: 5 },
  );
  assert.throws(
    () => buildJobInputs("predict_gap", { nmrH: "1.2", nmrC: "", limit: 5 }),
    /IR 或 Raman/,
  );
  assert.throws(() => parseShifts("1 NaN"), /有限数值/);
  assert.throws(() => parseShifts("1 Infinity"), /有限数值/);
  assert.throws(() => parseShifts("1 two"), /有限数值/);
});
test("renders only actual matched spectral arrays and preserves modality", () => {
  assert.deepEqual(
    resultSpectra({
      wavenumber: [400, 500],
      ir: [0.2, 0.8],
      raman: [3, 4],
    }).map((s) => s.modality),
    ["ir", "raman"],
  );
  assert.deepEqual(resultSpectra({ wavenumber: [400, 500], ir: [0.2] }), []);
  assert.deepEqual(
    resultSpectra({ wavenumber: [400, 500], ir: [NaN, 0.8] }),
    [],
  );
});

test("NMR separators never introduce zero peaks and values use decimal numeric syntax", () => {
  assert.deepEqual(parseShifts("1.2, 2.3; "), [1.2, 2.3]);
  assert.deepEqual(parseShifts(" , ; "), []);
  assert.throws(() => parseShifts("1 0x10"), /有限数值/);
});

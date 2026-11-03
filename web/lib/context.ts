import type {
  ContextReferences,
  Modality,
  Molecule,
  Spectrum,
} from "./types.ts";
import { parseShifts } from "./science.ts";

/** UI labels are captured with their references, independently of the editable workbench. */
export interface SelectedContext {
  references: ContextReferences;
  labels: Partial<Record<keyof ContextReferences, string>>;
}

export function validateMoleculeDraft(
  molecule: Pick<Molecule, "smiles"> | null,
  draftSmiles: string,
) {
  if (!molecule && draftSmiles.trim())
    throw new Error("请先解析输入的分子结构，再用于对话");
  if (molecule && draftSmiles.trim() !== molecule.smiles)
    throw new Error("结构已修改，请先重新解析");
}

export function selectWorkbenchContext(input: {
  molecule: Pick<Molecule, "id" | "smiles" | "formula"> | null;
  draftSmiles: string;
  spectra: Partial<Record<Modality, Pick<Spectrum, "id" | "name">>>;
  nmrH: string;
  nmrC: string;
}): SelectedContext {
  validateMoleculeDraft(input.molecule, input.draftSmiles);
  const references: ContextReferences = {};
  const labels: SelectedContext["labels"] = {};
  if (input.molecule) {
    references.molecule_id = input.molecule.id;
    labels.molecule_id = `分子 · ${input.molecule.formula}`;
  }
  for (const modality of ["ir", "raman"] as const) {
    const spectrum = input.spectra[modality];
    if (spectrum) {
      references[`${modality}_id`] = spectrum.id;
      labels[`${modality}_id`] =
        `${modality === "ir" ? "IR" : "Raman"} · ${spectrum.name}`;
    }
  }
  const h = parseShifts(input.nmrH),
    c = parseShifts(input.nmrC);
  if (h.length) {
    references.nmr_h = h;
    labels.nmr_h = `¹H NMR · ${h.length} 个峰`;
  }
  if (c.length) {
    references.nmr_c = c;
    labels.nmr_c = `¹³C NMR · ${c.length} 个峰`;
  }
  return { references, labels };
}

export function removeContextField(
  selection: SelectedContext,
  key: keyof ContextReferences,
): SelectedContext {
  const references = { ...selection.references };
  const labels = { ...selection.labels };
  delete references[key];
  delete labels[key];
  return { references, labels };
}

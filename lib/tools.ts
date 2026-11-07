export type ToolSlug =
  | "structure-to-spectrum"
  | "spectrum-retrieval"
  | "spectrum-to-gap"
  | "spectrum-to-generation";

export interface ToolMeta {
  slug: ToolSlug;
  index: string;
  name: string;
  io: string;
  desc: string;
  bench: string;
}

export const TOOLS: ToolMeta[] = [
  {
    slug: "structure-to-spectrum",
    index: "01",
    name: "Structure to Spectrum",
    io: "SMILES → IR · Raman · H/C NMR",
    desc: "Four EquiformerV3 models predict Hessian and response tensors, reconstruct theoretical vibrational spectra in 400–4000 cm⁻¹, plus atom-level H/C NMR shifts.",
    bench: "1M theoretical · OpenMolSpec v1",
  },
  {
    slug: "spectrum-retrieval",
    index: "02",
    name: "Spectral Retrieval",
    io: "IR / Raman / NMR → Top-K molecules",
    desc: "Multimodal theoretical spectra are matched against the test-set molecule library; returns ranked candidates with structure drawings.",
    bench: "200k test set · spectral cosine / vib2mol embeddings",
  },
  {
    slug: "spectrum-to-gap",
    index: "03",
    name: "Spectrum to HOMO–LUMO Gap",
    io: "Multimodal spectra → gap (eV)",
    desc: "A shared spectroscopy transformer fuses IR, Raman and computed H/C shifts to predict the HOMO–LUMO gap, with fixed test-set MAE / R² reference.",
    bench: "1M · test 20,390 molecules",
  },
  {
    slug: "spectrum-to-generation",
    index: "04",
    name: "Spectrum to Structure",
    io: "Multimodal spectra → SMILES",
    desc: "Vib2Mol runs beam search on theoretical spectra to generate structure candidates, reranked and deduplicated by the matching head.",
    bench: "200k test · top-1 68.13% · top-5 80.02% · valid 97.67%",
  },
];

export const toolBySlug = (slug: string) => TOOLS.find((tool) => tool.slug === slug);

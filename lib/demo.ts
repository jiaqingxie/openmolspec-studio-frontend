import type {
  Candidate,
  GapResponse,
  PredictResponse,
  SampleResponse,
  StatusResponse,
} from "./api";
import type { ToolSlug } from "./tools";

const axis = Array.from({ length: 360 }, (_, i) => 400 + i * 10);

function peaks(intensities: [number, number][]): number[] {
  return axis.map(
    (x) =>
      intensities.reduce(
        (sum, [center, height]) => sum + height * Math.exp(-(((x - center) / 28) ** 2)),
        0,
      ) + Math.random() * 0.01,
  );
}

export const demoStatus = (): StatusResponse => ({
  device: "demo",
  tools: {
    "structure-to-spectrum": true,
    "spectrum-retrieval": true,
    "spectrum-to-gap": true,
    "spectrum-to-generation": true,
  } as Record<ToolSlug, boolean>,
});

export const demoSample = (): SampleResponse => ({
  ir: peaks([
    [740, 0.45],
    [1020, 0.3],
    [1465, 0.5],
    [1710, 0.85],
    [2950, 0.4],
    [3300, 0.55],
  ]),
  raman: peaks([
    [830, 0.35],
    [1180, 0.5],
    [1610, 0.8],
    [3060, 0.4],
  ]),
  nmr_h: [1.24, 2.38, 7.1, 7.32, 7.48, 8.05, 11.2],
  nmr_c: [18.2, 42.8, 124.1, 126.7, 130.5, 132.8, 169.4, 172.1],
  meta: {
    sample_id: "demo-0001",
    source: "OpenMolSpec test set (demo)",
    smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
  },
});

export const demoPredict = (): PredictResponse => ({
  wavenumber: axis,
  ir: peaks([
    [650, 0.35],
    [1030, 0.42],
    [1180, 0.3],
    [1490, 0.38],
    [1745, 0.9],
    [2900, 0.35],
    [3180, 0.45],
  ]),
  raman: peaks([
    [710, 0.3],
    [1000, 0.55],
    [1385, 0.42],
    [1605, 0.75],
    [3070, 0.5],
  ]),
  nmr_h: [2.35, 7.12, 7.34, 7.61, 8.02, 11.4],
  nmr_c: [21.5, 123.8, 126.2, 129.7, 131.4, 135.2, 168.9, 172.5],
  modes: [
    { frequency: 648.2, ir_activity: 0.41, raman_activity: 0.22 },
    { frequency: 1032.7, ir_activity: 0.55, raman_activity: 0.31 },
    { frequency: 1184.9, ir_activity: 0.28, raman_activity: 0.14 },
    { frequency: 1493.1, ir_activity: 0.39, raman_activity: 0.48 },
    { frequency: 1741.6, ir_activity: 0.92, raman_activity: 0.12 },
    { frequency: 2904.3, ir_activity: 0.34, raman_activity: 0.29 },
    { frequency: 3186.5, ir_activity: 0.46, raman_activity: 0.51 },
  ],
});

export const demoCandidates = (limit: number): Candidate[] => {
  const pool: [string, number][] = [
    ["CC(=O)OC1=CC=CC=C1C(=O)O", 0.9412],
    ["O=C(O)C1=CC=CC=C1O", 0.8873],
    ["CC(=O)NC1=CC=C(C=C1)O", 0.8421],
    ["CN1C=NC2=C1C(=O)N(C)C(=O)N2C", 0.7934],
    ["OC(=O)C1=CC=CC=C1C(=O)O", 0.7512],
    ["CC(C)Cc1ccc(cc1)C(C)C(=O)O", 0.7108],
    ["OCC1OC(O)C(O)C(O)C1O", 0.6642],
    ["c1ccc2c(c1)ccc3ccccc32", 0.6187],
    ["CCCCCCCCO", 0.5823],
    ["CCO", 0.5411],
    ["c1ccccc1", 0.5024],
    ["CCCC", 0.4789],
  ];
  return pool.slice(0, limit).map(([smiles, similarity]) => ({ smiles, similarity }));
};

export const demoGap = (): GapResponse => ({
  gap_ev: 4.872,
  benchmark_mae_ev: 0.113,
  benchmark_r2_ev: 0.986,
});

export const demoGenerate = (limit: number) => ({
  candidates: demoCandidates(limit).map((candidate) => ({
    ...candidate,
    score: candidate.similarity,
  })),
  note: "Demo mode: candidates are illustrative placeholders, not model output.",
});

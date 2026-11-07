"use client";
import { useRef, useState } from "react";
import { fetchSample } from "@/lib/api";
import { SpectrumChart } from "./spectrum-chart";

export interface ParsedSpectrum {
  wavenumber?: number[];
  intensity: number[];
}

async function parseSpectrumFile(file: File): Promise<ParsedSpectrum> {
  const text = await file.text();
  const rows = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => line.split(/[\s,;]+/).map(Number).filter((value) => Number.isFinite(value)));
  if (!rows.length) throw new Error(`${file.name}: no numeric rows`);
  const columns = Math.min(...rows.map((row) => row.length));
  if (columns === 1) return { intensity: rows.map((row) => row[0]) };
  return {
    wavenumber: rows.map((row) => row[0]),
    intensity: rows.map((row) => row[1]),
  };
}

function downsample(spectrum: ParsedSpectrum, target = 360): { x: number; y: number }[] {
  const { wavenumber, intensity } = spectrum;
  const points: { x: number; y: number }[] = [];
  for (let i = 0; i < intensity.length; i += 1) {
    points.push({ x: wavenumber ? wavenumber[i] : 400 + (i * 3600) / intensity.length, y: intensity[i] });
  }
  if (points.length <= target) return points;
  const step = points.length / target;
  return Array.from({ length: target }, (_, i) => points[Math.floor(i * step)]);
}

function parsePeaks(text: string): number[] {
  return text
    .split(/[,;\s]+/)
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
}

export function SpectrumInput({
  onQuery,
}: {
  onQuery: (query: {
    ir: ParsedSpectrum | null;
    raman: ParsedSpectrum | null;
    nmr_h: number[];
    nmr_c: number[];
    meta?: { sample_id: string; source: string; smiles: string };
    ready: boolean;
    demo: boolean;
  }) => void;
}) {
  const [ir, setIr] = useState<ParsedSpectrum | null>(null);
  const [raman, setRaman] = useState<ParsedSpectrum | null>(null);
  const [nmrHText, setNmrHText] = useState("");
  const [nmrCText, setNmrCText] = useState("");
  const [meta, setMeta] = useState<{ sample_id: string; source: string; smiles: string } | undefined>();
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const irInput = useRef<HTMLInputElement>(null);
  const ramanInput = useRef<HTMLInputElement>(null);

  function emit(
    nextIr: ParsedSpectrum | null,
    nextRaman: ParsedSpectrum | null,
    nextH: string,
    nextC: string,
    nextMeta: typeof meta,
    nextDemo: boolean,
  ) {
    onQuery({
      ir: nextIr,
      raman: nextRaman,
      nmr_h: parsePeaks(nextH),
      nmr_c: parsePeaks(nextC),
      meta: nextMeta,
      ready: nextIr !== null || nextRaman !== null,
      demo: nextDemo,
    });
  }

  async function loadExample() {
    setError(null);
    const result = await fetchSample();
    const parsed: ParsedSpectrum = { intensity: result.data.ir };
    const parsedRaman: ParsedSpectrum = { intensity: result.data.raman };
    const hText = result.data.nmr_h.map((value) => Number(value.toPrecision(4))).join(", ");
    const cText = result.data.nmr_c.map((value) => Number(value.toPrecision(4))).join(", ");
    setIr(parsed);
    setRaman(parsedRaman);
    setNmrHText(hText);
    setNmrCText(cText);
    setMeta(result.data.meta);
    setDemo(result.demo);
    emit(parsed, parsedRaman, hText, cText, result.data.meta, result.demo);
  }

  async function handleFile(kind: "ir" | "raman", file: File | undefined) {
    if (!file) return;
    setError(null);
    try {
      const parsed = await parseSpectrumFile(file);
      if (kind === "ir") {
        setIr(parsed);
        setMeta(undefined);
        emit(parsed, raman, nmrHText, nmrCText, undefined, demo);
      } else {
        setRaman(parsed);
        setMeta(undefined);
        emit(ir, parsed, nmrHText, nmrCText, undefined, demo);
      }
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
    }
  }

  const chartSeries = [];
  if (ir) chartSeries.push({ name: "IR", color: "#0c5da5", points: downsample(ir) });
  if (raman) chartSeries.push({ name: "Raman", color: "#00a36c", points: downsample(raman) });

  return (
    <div>
      <div className="mb-2 d-flex flex-wrap align-items-center gap-2">
        <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => void loadExample()}>
          Load test-set example
        </button>
        {meta && (
          <span className="font-monospace text-secondary" style={{ fontSize: "0.75rem" }}>
            {meta.sample_id} · {meta.smiles}
          </span>
        )}
      </div>
      <div className="row g-3">
        <div className="col-md-6">
          <label className="form-label">Theoretical IR spectrum</label>
          <input
            ref={irInput}
            type="file"
            accept=".csv,.txt,.tsv,.dat"
            className="form-control form-control-sm"
            onChange={(event) => void handleFile("ir", event.target.files?.[0])}
          />
          <span className="text-help">One column intensity, or two columns wavenumber / intensity.</span>
        </div>
        <div className="col-md-6">
          <label className="form-label">Theoretical Raman spectrum</label>
          <input
            ref={ramanInput}
            type="file"
            accept=".csv,.txt,.tsv,.dat"
            className="form-control form-control-sm"
            onChange={(event) => void handleFile("raman", event.target.files?.[0])}
          />
          <span className="text-help">Optional; IR and Raman jointly improve ranking.</span>
        </div>
      </div>
      {error && (
        <div className="alert alert-danger py-2 px-3 mt-2 mb-0" style={{ fontSize: "0.85rem" }}>
          {error}
        </div>
      )}
      <div className="mt-3">
        <div className="form-label mb-1">Computed H / C NMR shifts (optional)</div>
        <div className="row g-3">
          <div className="col-md-6">
            <textarea
              value={nmrHText}
              onChange={(event) => {
                setNmrHText(event.target.value);
                emit(ir, raman, event.target.value, nmrCText, meta, demo);
              }}
              rows={2}
              spellCheck={false}
              className="form-control font-monospace"
              style={{ fontSize: "0.8rem" }}
              placeholder="1.24, 2.38, 7.10"
            />
            <span className="text-help">¹H shifts in ppm, comma or space separated.</span>
          </div>
          <div className="col-md-6">
            <textarea
              value={nmrCText}
              onChange={(event) => {
                setNmrCText(event.target.value);
                emit(ir, raman, nmrHText, event.target.value, meta, demo);
              }}
              rows={2}
              spellCheck={false}
              className="form-control font-monospace"
              style={{ fontSize: "0.8rem" }}
              placeholder="18.2, 42.8, 128.4"
            />
            <span className="text-help">¹³C shifts in ppm.</span>
          </div>
        </div>
      </div>
      {chartSeries.length > 0 && (
        <div className="mt-3">
          <SpectrumChart series={chartSeries} xLabel="wavenumber (cm⁻¹)" height={200} />
          <p className="figure-caption-text mt-1 mb-0">
            Preview of submitted spectra (downsampled for display); the model receives the
            full-resolution 1024-point grid.
          </p>
        </div>
      )}
      {ir === null && raman === null && (
        <div className="alert alert-info py-2 px-3 mt-3 mb-0" style={{ fontSize: "0.85rem" }}>
          Upload at least one spectrum file (IR or Raman), or load a test-set example. At least one
          vibrational spectrum is required; NMR shifts are optional but improve ranking.
        </div>
      )}
    </div>
  );
}

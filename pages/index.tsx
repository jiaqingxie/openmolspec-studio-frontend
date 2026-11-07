import Link from "next/link";
import { TOOLS } from "@/lib/tools";
import { useStatus } from "@/components/shell";

export default function Home() {
  const status = useStatus();
  return (
    <div>
      <nav aria-label="breadcrumb">
        <ol className="breadcrumb mb-2" style={{ fontSize: "0.8rem" }}>
          <li className="breadcrumb-item active" aria-current="page">
            Home
          </li>
        </ol>
      </nav>
      <h1 className="h4 mb-1">OpenMolSpec Studio — tool gallery</h1>
      <p className="text-secondary" style={{ maxWidth: "72ch", fontSize: "0.9rem", lineHeight: 1.6 }}>
        Four trained checkpoints exposed as one-click tools: forward prediction of theoretical IR,
        Raman and H/C NMR spectra from molecular structure, spectral retrieval over a 200k-molecule
        test library, HOMO–LUMO gap regression, and inverse generation of candidate structures from
        multimodal spectra. Every tool ships with example inputs, a real inference pass and
        downloadable results.
      </p>

      <div className="row g-3 mt-1">
        {TOOLS.map((tool) => {
          const ready = status ? status.data.tools[tool.slug] : undefined;
          return (
            <div className="col-md-6" key={tool.slug}>
              <div className="card h-100">
                <div className="card-body d-flex flex-column">
                  <div className="d-flex justify-content-between align-items-start mb-1">
                    <h2 className="h6 mb-0" style={{ color: "var(--oms-primary)" }}>
                      {tool.index} · {tool.name}
                    </h2>
                    {ready !== undefined && (
                      <span
                        className={`badge ${ready ? "text-bg-success" : "text-bg-danger"}`}
                        style={{ fontWeight: 500 }}
                      >
                        {ready ? "READY" : "MISSING"}
                      </span>
                    )}
                  </div>
                  <p className="mb-2 font-monospace" style={{ fontSize: "0.78rem", color: "#0b5394" }}>
                    {tool.io}
                  </p>
                  <p className="text-secondary mb-2" style={{ fontSize: "0.85rem", lineHeight: 1.55 }}>
                    {tool.desc}
                  </p>
                  <div className="mt-auto d-flex justify-content-between align-items-center">
                    <span className="text-secondary font-monospace" style={{ fontSize: "0.72rem" }}>
                      {tool.bench}
                    </span>
                    <Link href={`/tool/${tool.slug}`} className="btn btn-sm btn-primary">
                      Launch tool →
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="card mt-3">
        <div className="card-body py-2">
          <p className="mb-0 text-secondary" style={{ fontSize: "0.8rem", lineHeight: 1.6 }}>
            <strong>Notes.</strong> All spectra live in the theoretical 400–4000 cm⁻¹ domain. On
            CPU-only deployments, retrieval and generation fall back to the cached cosine baseline;
            each tool page reports which backend produced its results. If a tool shows MISSING, its
            checkpoint was not found under the configured assets root.
          </p>
        </div>
      </div>
    </div>
  );
}

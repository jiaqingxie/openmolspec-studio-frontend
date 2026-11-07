"use client";
import dynamic from "next/dynamic";
import { useState } from "react";

const KetcherPanel = dynamic(() => import("./ketcher-panel"), {
  ssr: false,
  loading: () => (
    <div
      className="border rounded d-flex align-items-center justify-content-center text-secondary"
      style={{ height: 430, fontSize: "0.85rem" }}
    >
      loading structure editor…
    </div>
  ),
});

export const EXAMPLES: [string, string][] = [
  ["Aspirin", "CC(=O)OC1=CC=CC=C1C(=O)O"],
  ["Caffeine", "CN1C=NC2=C1C(=O)N(C)C(=O)N2C"],
  ["Paracetamol", "CC(=O)NC1=CC=C(C=C1)O"],
  ["Ethanol", "CCO"],
];

export function MoleculeInput({
  smiles,
  onChange,
}: {
  smiles: string;
  onChange: (smiles: string) => void;
}) {
  const [tab, setTab] = useState<"draw" | "smiles">("smiles");
  return (
    <div>
      <div className="mb-2 d-flex align-items-center justify-content-between flex-wrap gap-2">
        <ul className="nav nav-tabs mb-0" role="tablist">
          <li className="nav-item">
            <button
              type="button"
              className={`nav-link py-1 ${tab === "smiles" ? "active" : ""}`}
              onClick={() => setTab("smiles")}
            >
              SMILES
            </button>
          </li>
          <li className="nav-item">
            <button
              type="button"
              className={`nav-link py-1 ${tab === "draw" ? "active" : ""}`}
              onClick={() => setTab("draw")}
            >
              Draw structure
            </button>
          </li>
        </ul>
        <span className="text-secondary" style={{ fontSize: "0.78rem" }}>
          Examples:{" "}
          {EXAMPLES.map(([label, value], index) => (
            <span key={label}>
              {index > 0 && " · "}
              <a
                href="#"
                onClick={(event) => {
                  event.preventDefault();
                  setTab("smiles");
                  onChange(value);
                }}
                style={smiles === value ? { fontWeight: 700 } : undefined}
              >
                {label}
              </a>
            </span>
          ))}
        </span>
      </div>
      {tab === "smiles" ? (
        <>
          <textarea
            value={smiles}
            onChange={(event) => onChange(event.target.value)}
            spellCheck={false}
            rows={3}
            className="form-control font-monospace"
            style={{ fontSize: "0.85rem" }}
            placeholder="CC(=O)OC1=CC=CC=C1C(=O)O"
          />
          <span className="text-help mt-1">
            One molecule per run. The structure is embedded to a 3D conformer before inference.
          </span>
        </>
      ) : (
        <KetcherPanel initialSmiles={smiles} onApply={onChange} />
      )}
    </div>
  );
}

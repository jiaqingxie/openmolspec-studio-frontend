"use client";
import { useState } from "react";
import { structureImageUrl, type Candidate } from "@/lib/api";

export function CandidateList({
  candidates,
  scoreLabel = "similarity",
}: {
  candidates: Candidate[];
  scoreLabel?: string;
}) {
  if (!candidates.length) return null;
  const csv = toCsv(candidates, scoreLabel);
  return (
    <div>
      <div className="d-flex justify-content-end mb-2">
        <a href={csv} download="openmolspec_candidates.csv" className="btn btn-sm btn-outline-primary">
          Download CSV
        </a>
      </div>
      <div className="table-responsive">
        <table className="table table-striped table-hover align-middle mb-1">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Structure</th>
              <th scope="col">SMILES</th>
              <th scope="col" className="text-end">
                {scoreLabel}
              </th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((candidate, index) => (
              <CandidateRow key={`${candidate.smiles}-${index}`} rank={index + 1} candidate={candidate} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CandidateRow({ rank, candidate }: { rank: number; candidate: Candidate }) {
  const [imageFailed, setImageFailed] = useState(false);
  const score = candidate.similarity ?? candidate.score;
  return (
    <tr>
      <td className="font-monospace text-secondary" style={{ fontSize: "0.8rem" }}>
        {rank}
      </td>
      <td>
        <div
          className="border bg-white d-flex align-items-center justify-content-center"
          style={{ width: 92, height: 56 }}
        >
          {imageFailed ? (
            <span className="text-secondary" style={{ fontSize: "0.7rem" }}>
              n/a
            </span>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={structureImageUrl(candidate.smiles)}
              alt={`candidate ${rank}`}
              style={{ maxWidth: "100%", maxHeight: "100%" }}
              onError={() => setImageFailed(true)}
            />
          )}
        </div>
      </td>
      <td>
        <code style={{ fontSize: "0.8rem", wordBreak: "break-all" }}>{candidate.smiles}</code>
      </td>
      <td className="text-end font-monospace" style={{ fontSize: "0.85rem" }}>
        {score !== undefined ? score.toFixed(4) : "—"}
      </td>
    </tr>
  );
}

export function toCsv(candidates: Candidate[], scoreLabel = "similarity") {
  const header = `rank,smiles,${scoreLabel}\n`;
  const body = candidates
    .map((candidate, index) => {
      const score = candidate.similarity ?? candidate.score ?? "";
      return `${index + 1},"${candidate.smiles}",${score}`;
    })
    .join("\n");
  return `data:text/csv;charset=utf-8,${encodeURIComponent(header + body)}`;
}

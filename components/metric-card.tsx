"use client";
export function StatTable({ rows }: { rows: { label: string; value: string; detail?: string }[] }) {
  return (
    <div className="table-responsive">
      <table className="table align-middle mb-0">
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <td className="text-secondary" style={{ width: "34%", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                {row.label}
              </td>
              <td className="font-monospace" style={{ fontSize: "1.35rem", fontWeight: 600 }}>
                {row.value}
              </td>
              {rows.some((item) => item.detail) && (
                <td className="text-secondary" style={{ fontSize: "0.82rem" }}>
                  {row.detail}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CsvButton({ csv, filename, label }: { csv: string; filename: string; label: string }) {
  return (
    <a
      href={`data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`}
      download={filename}
      className="btn btn-sm btn-outline-primary"
    >
      {label}
    </a>
  );
}

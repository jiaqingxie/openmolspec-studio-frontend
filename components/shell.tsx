import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";
import { fetchStatus, type StatusResponse } from "@/lib/api";
import { TOOLS } from "@/lib/tools";

export function useStatus() {
  const [status, setStatus] = useState<{ data: StatusResponse; demo: boolean } | null>(null);
  useEffect(() => {
    let active = true;
    void fetchStatus().then((result) => {
      if (active) setStatus(result);
    });
    return () => {
      active = false;
    };
  }, []);
  return status;
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const status = useStatus();
  const current = router.asPath;

  return (
    <div className="d-flex flex-column min-vh-100">
      <nav className="navbar navbar-expand oms-navbar py-2">
        <div className="container-fluid" style={{ maxWidth: 1140 }}>
          <Link href="/" className="navbar-brand d-flex align-items-center gap-2 fw-semibold" style={{ fontSize: "1rem" }}>
            <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">
              <path
                d="M16 3.5 L25 8.75 V19.25 L16 24.5 L7 19.25 V8.75 Z"
                fill="none"
                stroke="#7fb3e0"
                strokeWidth="2.4"
                strokeLinejoin="round"
              />
              <path
                d="M10.8 18.2 C12.2 18.2 12.6 12.2 14 12.2 C15.4 12.2 15.7 16 17 16 C18.3 16 18.8 9.8 21.2 9.8"
                fill="none"
                stroke="#5fd3a5"
                strokeWidth="2.1"
                strokeLinecap="round"
              />
              <circle cx="25" cy="5.6" r="2.1" fill="#7fb3e0" />
            </svg>
            OpenMolSpec Studio
          </Link>
          <ul className="navbar-nav flex-row gap-1 ms-auto" style={{ fontSize: "0.875rem" }}>
            <li className="nav-item">
              <Link href="/" className={`nav-link ${current === "/" ? "active" : ""}`}>
                Overview
              </Link>
            </li>
            {TOOLS.map((tool) => (
              <li className="nav-item" key={tool.slug}>
                <Link
                  href={`/tool/${tool.slug}`}
                  className={`nav-link ${current === `/tool/${tool.slug}` ? "active" : ""}`}
                >
                  {tool.index}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </nav>

      <div className="bg-white border-bottom">
        <div className="container-fluid py-1" style={{ maxWidth: 1140 }}>
          <span className="text-secondary" style={{ fontSize: "0.75rem" }}>
            Local inference service · theoretical domain 400–4000 cm⁻¹ ·{" "}
            {status ? (status.demo ? "demo data (backend offline)" : `device: ${status.data.device}`) : "connecting…"}
          </span>
        </div>
      </div>

      <main className="container-fluid py-4" style={{ maxWidth: 1140 }}>
        {children}
      </main>

      <footer className="border-top bg-white mt-auto">
        <div className="container-fluid py-3 d-flex flex-wrap justify-content-between gap-2" style={{ maxWidth: 1140 }}>
          <span className="text-secondary" style={{ fontSize: "0.75rem" }}>
            OpenMolSpec Studio · v1 checkpoints · no data leaves this machine
          </span>
          <span className="text-secondary" style={{ fontSize: "0.75rem" }}>
            {TOOLS.map((tool) => {
              const ready = status ? status.data.tools[tool.slug] : undefined;
              return (
                <span key={tool.slug} className="me-3">
                  {tool.index}{" "}
                  <span className={ready === undefined ? "text-secondary" : ready ? "text-success" : "text-danger"}>
                    {ready === undefined ? "···" : ready ? "✓" : "✗"}
                  </span>
                </span>
              );
            })}
          </span>
        </div>
      </footer>
    </div>
  );
}

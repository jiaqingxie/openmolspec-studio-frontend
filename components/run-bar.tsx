"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export type RunState =
  | { phase: "idle" }
  | { phase: "running"; since: number }
  | { phase: "done"; seconds: number }
  | { phase: "error"; message: string };

export function useRun() {
  const [state, setState] = useState<RunState>({ phase: "idle" });
  const run = useCallback(async (task: () => Promise<void>) => {
    const since = performance.now();
    setState({ phase: "running", since });
    try {
      await task();
      setState({ phase: "done", seconds: (performance.now() - since) / 1000 });
    } catch (error) {
      setState({
        phase: "error",
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }, []);
  return { state, run };
}

export function RunBar({
  label,
  state,
  disabled,
  onRun,
}: {
  label: string;
  state: RunState;
  disabled?: boolean;
  onRun: () => void;
}) {
  const [tick, setTick] = useState(0);
  const raf = useRef<number | null>(null);
  useEffect(() => {
    if (state.phase === "running") {
      const loop = () => {
        setTick((value) => value + 1);
        raf.current = requestAnimationFrame(loop);
      };
      raf.current = requestAnimationFrame(loop);
      return () => {
        if (raf.current) cancelAnimationFrame(raf.current);
      };
    }
  }, [state.phase]);
  void tick;

  const elapsed =
    state.phase === "running" ? ((performance.now() - state.since) / 1000).toFixed(1) : null;

  return (
    <div className="card">
      <div className="card-body py-2 px-3 d-flex flex-column gap-2">
        <div className="d-flex flex-wrap align-items-center gap-2">
          <button
            type="button"
            onClick={onRun}
            disabled={disabled || state.phase === "running"}
            className="btn btn-primary btn-sm"
          >
            {state.phase === "running" ? (
              <>
                <span
                  className="spinner-border spinner-border-sm me-1"
                  style={{ width: "0.8rem", height: "0.8rem" }}
                  aria-hidden="true"
                />
                Running…
              </>
            ) : (
              label
            )}
          </button>
          {elapsed !== null && (
            <span className="font-monospace text-secondary" style={{ fontSize: "0.78rem" }}>
              {elapsed}s elapsed
            </span>
          )}
          {state.phase === "done" && (
            <span className="badge text-bg-success" style={{ fontWeight: 500 }}>
              completed in {state.seconds.toFixed(1)}s
            </span>
          )}
          {disabled && state.phase === "idle" && (
            <span className="text-secondary" style={{ fontSize: "0.78rem" }}>
              provide input above to enable
            </span>
          )}
        </div>
        {state.phase === "error" && (
          <div className="alert alert-danger py-2 px-3 mb-0" style={{ fontSize: "0.85rem" }} role="alert">
            <strong>Run failed.</strong> {state.message}
          </div>
        )}
      </div>
    </div>
  );
}

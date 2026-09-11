import { useState } from "react";
import { Link } from "react-router-dom";

import { useAssembleCases, useRunDetection } from "@/api/hooks";
import { ApiError } from "@/api/client";
import type { AssembleSummary, DetectionSummary } from "@/api/types";
import { useAuthStore } from "@/stores/authStore";

import { resolveNewCaseForAccount } from "./resolveCase";

type Phase = "idle" | "detecting" | "assembling" | "resolving" | "done" | "error";

/**
 * RBAC placement note: both POST /detection/run and POST /cases/assemble
 * are admin-only (blueprint §11.3 "Run detection batch"; cases.py gates
 * /assemble the same way — see its docstring). Rather than let a
 * non-admin click this and eat a 403, the button is disabled with an
 * explanation instead — matching the brief's "hide or disable... don't
 * just let them click it and fail."
 *
 * Placed on the data-entry screen itself (not a persistent nav action):
 * the natural moment to run detection is right after entering the data
 * that's supposed to trip it — a nav-level button elsewhere would need
 * its own account-selection UI to mean anything, which doesn't exist.
 */
export function DetectionRunner({ accountId }: { accountId: string }) {
  const role = useAuthStore((s) => s.user?.role);
  const isAdmin = role === "admin";

  const [phase, setPhase] = useState<Phase>("idle");
  const [detection, setDetection] = useState<DetectionSummary | null>(null);
  const [assembly, setAssembly] = useState<AssembleSummary | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runDetection = useRunDetection();
  const assembleCases = useAssembleCases();

  async function handleRun() {
    setError(null);
    setPhase("detecting");
    try {
      const detectionResult = await runDetection.mutateAsync();
      setDetection(detectionResult);

      setPhase("assembling");
      const assembleResult = await assembleCases.mutateAsync();
      setAssembly(assembleResult);

      setPhase("resolving");
      const resolvedCaseId = await resolveNewCaseForAccount(accountId, assembleResult.cases_created);
      setCaseId(resolvedCaseId);

      setPhase("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong running detection.");
      setPhase("error");
    }
  }

  const running = phase === "detecting" || phase === "assembling" || phase === "resolving";

  return (
    <div className="flex flex-col gap-3 border-t border-rule pt-4">
      <h2 className="font-ui text-sm font-semibold text-ink">Step 4 — Run detection</h2>

      {!isAdmin && (
        <p className="font-ui text-2xs text-caution">
          Only an admin can run detection (blueprint §11.3). Signed in as {role ?? "unknown"} — log out and use the
          admin demo account to run this step.
        </p>
      )}

      <button
        onClick={handleRun}
        disabled={!isAdmin || running}
        className="self-start rounded-sm border border-ink bg-ink px-3 py-1.5 font-ui text-xs font-medium text-paper disabled:opacity-50"
      >
        {running ? "Running…" : "Run detection"}
      </button>

      {running && <RunningSkeleton phase={phase} />}

      {error && <p className="font-ui text-xs text-critical">{error}</p>}

      {phase === "done" && detection && assembly && (
        <div className="flex flex-col gap-2 rounded-sm border border-rule bg-canvas p-3">
          <div className="grid grid-cols-2 gap-3 font-data text-2xs text-ink-muted">
            <div>
              <p className="font-ui text-2xs uppercase tracking-wide text-ink-faint">Detection</p>
              <p>accounts_evaluated: {detection.accounts_evaluated}</p>
              <p>alerts_created: {detection.alerts_created}</p>
              <p>
                band_counts: {Object.entries(detection.band_counts).map(([band, n]) => `${band}=${n}`).join(", ") || "—"}
              </p>
            </div>
            <div>
              <p className="font-ui text-2xs uppercase tracking-wide text-ink-faint">Case assembly</p>
              <p>cases_created: {assembly.cases_created}</p>
              <p>cases_reused: {assembly.cases_reused}</p>
              <p>alerts_linked: {assembly.alerts_linked}</p>
            </div>
          </div>

          {caseId ? (
            <Link
              to={`/cases/${caseId}`}
              className="mt-1 self-start rounded-sm border border-verified bg-verified-bg px-3 py-1.5 font-ui text-xs font-medium text-verified"
            >
              Open the new case →
            </Link>
          ) : (
            <p className="font-ui text-2xs text-ink-faint">
              Couldn't automatically identify a new case for this account (it may not have tripped a rule, or already
              had one). <Link to="/" className="text-trace hover:underline">Check the Case Queue →</Link>
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function RunningSkeleton({ phase }: { phase: Phase }) {
  const label =
    phase === "detecting" ? "Running the rule engine + ML ensemble…" : phase === "assembling" ? "Assembling cases from alerts…" : "Looking up the new case…";
  return (
    <div className="flex flex-col gap-2" aria-live="polite" aria-busy="true">
      <p className="font-ui text-2xs text-ink-muted">{label}</p>
      <div className="flex flex-col gap-1.5">
        {["92%", "70%"].map((w, i) => (
          <div key={i} className="h-[14px] rounded-sm bg-rule opacity-50" style={{ width: w }} />
        ))}
      </div>
    </div>
  );
}

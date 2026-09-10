import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useCases, useEditNarrative, useEvidencePack, useGenerateNarrative, useNarrative } from "@/api/hooks";

import { CaseRail } from "./CaseRail";
import { EditableNarrative } from "./EditableNarrative";
import { EvidencePanel } from "./EvidencePanel";
import { GenerationSkeleton } from "./GenerationSkeleton";
import { NarrativePane } from "./NarrativePane";
import { useLatestNarrativeId } from "./useLatestNarrativeId";
import { VerificationCard } from "./VerificationCard";
import { WorkspaceToolbar } from "./WorkspaceToolbar";

export function CaseWorkspacePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const { data: cases } = useCases();
  const caseSummary = cases?.find((c) => c.id === caseId);

  const { data: pack } = useEvidencePack(caseId);
  const { narrativeId: latestNarrativeId, isLoading: auditLoading } = useLatestNarrativeId(caseId);

  const [generatedId, setGeneratedId] = useState<string | undefined>(undefined);
  const activeNarrativeId = generatedId ?? latestNarrativeId;

  const { data: narrative, isLoading: narrativeLoading } = useNarrative(activeNarrativeId);
  // Until the audit trail (the only source we have for "does this case
  // already have a narrative") has loaded, we can't yet tell "no
  // narrative" apart from "haven't checked yet" — don't flash the empty
  // state in between.
  const stillResolvingNarrative = auditLoading && !generatedId;

  const [mode, setMode] = useState<"TEMPLATE" | "HYBRID">("TEMPLATE");
  const [isEditing, setIsEditing] = useState(false);
  const generate = useGenerateNarrative(caseId);
  const edit = useEditNarrative(narrative?.id);

  function handleRegenerate() {
    setIsEditing(false);
    generate.mutate(
      { mode },
      {
        onSuccess: (result) => setGeneratedId(result.id),
      },
    );
  }

  function handleSaveEdit(sentences: { text: string; section: string | null; evidence_keys: string[] }[]) {
    edit.mutate(sentences, {
      onSuccess: (result) => {
        setGeneratedId(result.id);
        setIsEditing(false);
      },
    });
  }

  return (
    <div className="flex h-screen flex-col bg-canvas">
      <header className="flex items-center gap-3 border-b border-rule bg-panel px-6 py-3">
        <Link to="/" className="font-ui text-xs text-ink-muted hover:text-ink">
          ← Case Queue
        </Link>
        <h1 className="font-data text-sm font-medium text-ink">{caseSummary?.case_ref ?? caseId}</h1>
        {caseSummary && <span className="font-ui text-xs text-ink-faint">{caseSummary.status}</span>}
        {narrative && narrative.version > 1 && (
          <Link
            to={`/cases/${caseId}/narratives/${narrative.id}/diff/${narrative.version - 1}`}
            className="font-ui text-xs text-ink-muted hover:text-ink"
          >
            Diff vs v{narrative.version - 1}
          </Link>
        )}
        <Link to={`/cases/${caseId}/audit`} className="ml-auto font-ui text-xs text-ink-muted hover:text-ink">
          Audit trail →
        </Link>
      </header>

      <WorkspaceToolbar
        mode={mode}
        onModeChange={setMode}
        onRegenerate={handleRegenerate}
        isGenerating={generate.isPending}
        isEditing={isEditing}
        onToggleEdit={() => setIsEditing((v) => !v)}
        hasNarrative={Boolean(narrative)}
      />

      {generate.isError && (
        <p className="border-b border-rule bg-critical-bg px-6 py-2 font-ui text-xs text-critical">
          Generation failed: {String(generate.error)}
        </p>
      )}

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <CaseRail pack={pack} />

        <main className="min-h-0 flex-1 overflow-y-auto bg-paper">
          {generate.isPending ? (
            <div className="mx-auto max-w-narrative px-8 py-8">
              <GenerationSkeleton />
            </div>
          ) : isEditing && narrative ? (
            <EditableNarrative narrative={narrative} onSave={handleSaveEdit} onCancel={() => setIsEditing(false)} isSaving={edit.isPending} />
          ) : stillResolvingNarrative || (narrativeLoading && activeNarrativeId) ? (
            <div className="mx-auto max-w-narrative px-8 py-8">
              <p className="font-ui text-xs text-ink-muted">Loading case…</p>
            </div>
          ) : narrative && pack ? (
            <NarrativePane narrative={narrative} evidenceItems={pack.items} />
          ) : (
            <div className="mx-auto max-w-narrative px-8 py-16 text-center">
              <p className="font-ui text-sm text-ink-muted">No narrative generated yet for this case.</p>
              <p className="mt-1 font-ui text-xs text-ink-faint">
                Use the toolbar above to generate one from the current evidence pack.
              </p>
            </div>
          )}
        </main>

        <aside className="min-h-0 w-[340px] shrink-0 overflow-y-auto border-l border-rule bg-panel">
          <VerificationCard
            verification={narrative?.verification ?? null}
            detailHref={narrative ? (check) => `/cases/${caseId}/narratives/${narrative.id}/verification?check=${check}` : undefined}
          />
          {pack && <EvidencePanel items={pack.items} />}
        </aside>
      </div>
    </div>
  );
}

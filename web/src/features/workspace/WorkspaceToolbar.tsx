import type { GenerationMode } from "@/api/types";

const MODES: Extract<GenerationMode, "TEMPLATE" | "HYBRID">[] = ["TEMPLATE", "HYBRID"];

export function WorkspaceToolbar({
  mode,
  onModeChange,
  onRegenerate,
  isGenerating,
  isEditing,
  onToggleEdit,
  hasNarrative,
}: {
  mode: "TEMPLATE" | "HYBRID";
  onModeChange: (m: "TEMPLATE" | "HYBRID") => void;
  onRegenerate: () => void;
  isGenerating: boolean;
  isEditing: boolean;
  onToggleEdit: () => void;
  hasNarrative: boolean;
}) {
  return (
    <div className="flex items-center gap-3 border-b border-rule bg-panel px-6 py-3">
      <div className="flex overflow-hidden rounded-sm border border-rule">
        {MODES.map((m) => (
          <button
            key={m}
            onClick={() => onModeChange(m)}
            aria-pressed={mode === m}
            disabled={isGenerating}
            className={`px-2 py-1 font-ui text-xs ${mode === m ? "bg-ink text-paper" : "bg-paper text-ink-muted hover:bg-canvas"}`}
          >
            {m}
          </button>
        ))}
      </div>

      <button
        onClick={onRegenerate}
        disabled={isGenerating}
        className="rounded-sm border border-rule bg-paper px-3 py-1.5 font-ui text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
      >
        {isGenerating ? "Generating…" : hasNarrative ? "Regenerate" : "Generate narrative"}
      </button>

      <button
        onClick={onToggleEdit}
        disabled={!hasNarrative || isGenerating}
        aria-pressed={isEditing}
        className={`rounded-sm border px-3 py-1.5 font-ui text-xs font-medium disabled:opacity-50 ${
          isEditing ? "border-trace bg-trace-bg text-trace" : "border-rule bg-paper text-ink hover:bg-canvas"
        }`}
      >
        {isEditing ? "Editing…" : "Edit"}
      </button>

      <button
        disabled
        title="Review workflow is not implemented yet (Part 6a scope note) — no-op for now."
        className="ml-auto rounded-sm border border-rule bg-paper px-3 py-1.5 font-ui text-xs font-medium text-ink-faint opacity-50"
      >
        Submit for review
      </button>
    </div>
  );
}

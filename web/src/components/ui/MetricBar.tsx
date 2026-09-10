/** The same thin-bar-with-label pattern used for typology weights in the
 * Case Workspace's rail (CaseRail.tsx) — reused here so the metrics
 * screen reads as part of the same product, not a bolted-on dashboard. */
export function MetricBar({ label, value, displayValue, fraction }: { label: string; value: string; displayValue?: string; fraction: number }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-ui text-xs text-ink">{label}</span>
        <span className="font-data text-xs text-ink-muted">{displayValue ?? value}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-sm bg-canvas">
        <div className="h-full bg-ink-faint" style={{ width: `${Math.max(0, Math.min(fraction, 1)) * 100}%` }} />
      </div>
    </div>
  );
}

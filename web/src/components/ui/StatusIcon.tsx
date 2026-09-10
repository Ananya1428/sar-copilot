import { AlertTriangle, Check, X } from "lucide-react";

export type Status = "verified" | "caution" | "critical";

const CONFIG: Record<Status, { Icon: typeof Check; label: string; className: string }> = {
  verified: { Icon: Check, label: "Passed", className: "text-verified" },
  caution: { Icon: AlertTriangle, label: "Caution", className: "text-caution" },
  critical: { Icon: X, label: "Failed", className: "text-critical" },
};

/**
 * Verification status conveyed by icon + text, never colour alone
 * (blueprint §18 accessibility floor).
 */
export function StatusIcon({ status, label }: { status: Status; label?: string }) {
  const { Icon, label: defaultLabel, className } = CONFIG[status];
  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <Icon size={14} strokeWidth={2.25} aria-hidden="true" />
      <span className="text-2xs font-ui font-medium uppercase tracking-wide">{label ?? defaultLabel}</span>
    </span>
  );
}

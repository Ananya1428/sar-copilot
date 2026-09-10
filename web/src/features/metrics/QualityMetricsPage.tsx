import { Link } from "react-router-dom";

import { useQualityMetrics } from "@/api/hooks";
import { MetricBar } from "@/components/ui/MetricBar";
import { CHECK_NAMES } from "@/api/types";
import { titleCase } from "@/lib/format";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border border-rule bg-panel p-4">
      <h2 className="mb-3 font-ui text-2xs font-semibold uppercase tracking-wide text-ink-faint">{title}</h2>
      {children}
    </section>
  );
}

export function QualityMetricsPage() {
  const { data: metrics, isLoading, error } = useQualityMetrics();

  return (
    <div className="min-h-full bg-canvas">
      <header className="flex items-center gap-3 border-b border-rule bg-panel px-6 py-4">
        <Link to="/" className="font-ui text-xs text-ink-muted hover:text-ink">
          ← Case Queue
        </Link>
        <h1 className="font-ui text-lg font-semibold text-ink">Quality Metrics</h1>
      </header>

      <main className="mx-auto flex max-w-4xl flex-col gap-4 px-6 py-6">
        {error ? (
          <p className="font-ui text-sm text-critical">Could not reach the backend: {String(error)}</p>
        ) : isLoading || !metrics ? (
          <p className="font-ui text-sm text-ink-muted">Loading…</p>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-4">
              <Section title="Narratives">
                <p className="font-data text-xl text-ink">{metrics.narrative_count}</p>
                <p className="font-ui text-2xs text-ink-faint">{metrics.verification_report_count} verification reports</p>
              </Section>
              <Section title="Human edit rate">
                <p className="font-data text-xl text-ink">
                  {metrics.human_edit_rate.value !== null ? `${(metrics.human_edit_rate.value * 100).toFixed(1)}%` : "—"}
                </p>
                <p className="font-ui text-2xs text-ink-faint">
                  {metrics.human_edit_rate.narratives_with_version_gt_1} of {metrics.human_edit_rate.total_narratives} versioned &gt; 1
                </p>
              </Section>
              <Section title="Generation latency">
                {metrics.generation_latency.available ? (
                  <p className="font-data text-xl text-ink">—</p>
                ) : (
                  <p className="font-ui text-xs text-caution">Not yet instrumented</p>
                )}
              </Section>
            </div>

            <Section title="Verification pass rate by generation mode">
              <div className="flex flex-col gap-3">
                {Object.entries(metrics.pass_rate_by_mode).map(([mode, rate]) => {
                  const unverified = metrics.unverified_narratives_by_mode[mode] ?? 0;
                  return (
                    <div key={mode}>
                      <MetricBar
                        label={mode}
                        value=""
                        displayValue={rate !== null ? `${(rate * 100).toFixed(0)}%` : "no data"}
                        fraction={rate ?? 0}
                      />
                      {unverified > 0 && (
                        <p className="mt-0.5 font-ui text-2xs text-ink-faint">
                          {unverified} narrative{unverified === 1 ? "" : "s"} in this mode {unverified === 1 ? "has" : "have"} no
                          verification report and {unverified === 1 ? "is" : "are"} excluded from this rate.
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </Section>

            <Section title="Mean overall score by generation mode">
              <div className="flex flex-col gap-3">
                {Object.entries(metrics.mean_overall_score_by_mode).map(([mode, score]) => (
                  <MetricBar key={mode} label={mode} value="" displayValue={score !== null ? score.toFixed(3) : "no data"} fraction={score ?? 0} />
                ))}
              </div>
            </Section>

            <Section title="Failure count by check">
              <div className="flex flex-col gap-3">
                {(() => {
                  const max = Math.max(1, ...CHECK_NAMES.map((n) => metrics.failure_count_by_check[n] ?? 0));
                  return CHECK_NAMES.map((name) => (
                    <MetricBar
                      key={name}
                      label={titleCase(name)}
                      value=""
                      displayValue={String(metrics.failure_count_by_check[name] ?? 0)}
                      fraction={(metrics.failure_count_by_check[name] ?? 0) / max}
                    />
                  ));
                })()}
              </div>
            </Section>

            <p className="font-ui text-2xs text-ink-faint">{metrics.human_edit_rate.note}</p>
            <p className="font-ui text-2xs text-ink-faint">{metrics.generation_latency.note}</p>
          </>
        )}
      </main>
    </div>
  );
}

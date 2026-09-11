import { useState } from "react";
import { Link } from "react-router-dom";

import type { AccountRecord, CustomerRecord } from "@/api/types";
import { AuthBadge } from "@/features/auth/AuthBadge";

import { AccountStep } from "./AccountStep";
import { CustomerStep } from "./CustomerStep";
import { DetectionRunner } from "./DetectionRunner";
import { TransactionStep } from "./TransactionStep";

type Step = "customer" | "account" | "transactions" | "detection";

/**
 * Part 8b's three endpoints form a strict dependency chain (a Transaction
 * needs an Account, which needs a Customer), so this is a sequential
 * flow rather than one combined form — each step can only exist once the
 * previous one's real id comes back from the backend.
 */
export function DataEntryPage() {
  const [step, setStep] = useState<Step>("customer");
  const [customer, setCustomer] = useState<CustomerRecord | null>(null);
  const [account, setAccount] = useState<AccountRecord | null>(null);

  return (
    <div className="min-h-full bg-canvas">
      <header className="flex items-center gap-3 border-b border-rule bg-panel px-6 py-3">
        <Link to="/" className="font-ui text-xs text-ink-muted hover:text-ink">
          ← Case Queue
        </Link>
        <h1 className="font-ui text-sm font-semibold text-ink">Add data</h1>
        <div className="ml-auto">
          <AuthBadge />
        </div>
      </header>

      <main className="mx-auto max-w-xl px-6 py-6">
        <StepIndicator step={step} />

        <div className="mt-4 rounded-md border border-rule bg-panel p-4">
          {step === "customer" && (
            <CustomerStep
              onCreated={(c) => {
                setCustomer(c);
                setStep("account");
              }}
            />
          )}

          {step === "account" && customer && (
            <AccountStep
              customer={customer}
              onCreated={(a) => {
                setAccount(a);
                setStep("transactions");
              }}
            />
          )}

          {step === "transactions" && account && <TransactionStep account={account} onDone={() => setStep("detection")} />}

          {step === "detection" && account && (
            <div className="flex flex-col gap-4">
              <p className="font-ui text-xs text-ink-muted">
                Data entry complete for account {account.account_ref}. Run detection to see whether it trips a rule.
              </p>
              <DetectionRunner accountId={account.id} />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function StepIndicator({ step }: { step: Step }) {
  const steps: { id: Step; label: string }[] = [
    { id: "customer", label: "Customer" },
    { id: "account", label: "Account" },
    { id: "transactions", label: "Transactions" },
    { id: "detection", label: "Detection" },
  ];
  const activeIndex = steps.findIndex((s) => s.id === step);

  return (
    <ol className="flex items-center gap-2 font-ui text-2xs">
      {steps.map((s, i) => (
        <li key={s.id} className="flex items-center gap-2">
          <span
            className={`rounded-sm border px-2 py-1 uppercase tracking-wide ${
              i === activeIndex
                ? "border-ink bg-ink text-paper"
                : i < activeIndex
                  ? "border-rule bg-canvas text-ink-muted"
                  : "border-rule bg-paper text-ink-faint"
            }`}
          >
            {i + 1}. {s.label}
          </span>
          {i < steps.length - 1 && <span className="text-ink-faint">→</span>}
        </li>
      ))}
    </ol>
  );
}

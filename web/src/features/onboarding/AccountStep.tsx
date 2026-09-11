import { useState } from "react";

import { useCreateAccount } from "@/api/hooks";
import { ApiError } from "@/api/client";
import type { AccountRecord, CustomerRecord } from "@/api/types";

import { Field, Select, TextInput } from "./Field";

const today = new Date().toISOString().slice(0, 10);

export function AccountStep({ customer, onCreated }: { customer: CustomerRecord; onCreated: (account: AccountRecord) => void }) {
  const [accountType, setAccountType] = useState<"checking" | "savings" | "business">("checking");
  const [currency, setCurrency] = useState("USD");
  const [openedAt, setOpenedAt] = useState(today);
  const [expectedVolume, setExpectedVolume] = useState("3000.00");

  const createAccount = useCreateAccount(customer.id);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    createAccount.mutate(
      { account_type: accountType, currency, opened_at: openedAt, expected_monthly_volume: expectedVolume },
      { onSuccess: onCreated },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <h2 className="font-ui text-sm font-semibold text-ink">Step 2 — Account</h2>
      <p className="font-ui text-2xs text-ink-faint">
        For {customer.legal_name} ({customer.customer_ref})
      </p>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Account type">
          <Select value={accountType} onChange={(e) => setAccountType(e.target.value as typeof accountType)}>
            <option value="checking">checking</option>
            <option value="savings">savings</option>
            <option value="business">business</option>
          </Select>
        </Field>
        <Field label="Currency">
          <TextInput
            required
            minLength={3}
            maxLength={3}
            value={currency}
            onChange={(e) => setCurrency(e.target.value.toUpperCase())}
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Opened at">
          <TextInput type="date" required max={today} value={openedAt} onChange={(e) => setOpenedAt(e.target.value)} />
        </Field>
        <Field label="Expected monthly volume">
          <TextInput
            type="number"
            required
            min="0.01"
            step="0.01"
            value={expectedVolume}
            onChange={(e) => setExpectedVolume(e.target.value)}
          />
        </Field>
      </div>

      {createAccount.isError && (
        <p className="font-ui text-xs text-critical">
          {createAccount.error instanceof ApiError ? createAccount.error.message : "Could not reach the backend."}
        </p>
      )}

      <button
        type="submit"
        disabled={createAccount.isPending}
        className="mt-1 self-start rounded-sm border border-ink bg-ink px-3 py-1.5 font-ui text-xs font-medium text-paper disabled:opacity-50"
      >
        {createAccount.isPending ? "Creating…" : "Create account →"}
      </button>
    </form>
  );
}

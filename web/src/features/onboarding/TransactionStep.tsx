import { useState } from "react";

import { useCreateTransaction } from "@/api/hooks";
import { ApiError } from "@/api/client";
import type { AccountRecord, TransactionRecord } from "@/api/types";

import { Field, Select, TextInput } from "./Field";

// datetime-local has no timezone of its own — treated as UTC wall-clock
// throughout (both this max attribute and the value sent on submit),
// which keeps the "not in the future" check consistent end to end without
// getting into local-timezone-offset edge cases for what's a local demo
// tool, not a multi-timezone production system.
function nowUtcForInput(): string {
  return new Date().toISOString().slice(0, 16);
}

export function TransactionStep({
  account,
  onDone,
}: {
  account: AccountRecord;
  onDone: () => void;
}) {
  const [added, setAdded] = useState<TransactionRecord[]>([]);
  const [justAdded, setJustAdded] = useState<TransactionRecord | null>(null);

  const [amount, setAmount] = useState("100.00");
  const [currency, setCurrency] = useState("USD");
  const [direction, setDirection] = useState<"credit" | "debit">("credit");
  const [channel, setChannel] = useState<"cash" | "wire" | "ach" | "card" | "check">("ach");
  const [executedAt, setExecutedAt] = useState(nowUtcForInput());
  const [counterpartyRef, setCounterpartyRef] = useState("");
  const [counterpartyCountry, setCounterpartyCountry] = useState("");
  const [isCash, setIsCash] = useState(false);

  const createTransaction = useCreateTransaction(account.id);

  function resetForm() {
    setAmount("100.00");
    setExecutedAt(nowUtcForInput());
    setCounterpartyRef("");
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    createTransaction.mutate(
      {
        amount,
        currency,
        direction,
        channel,
        executed_at: `${executedAt}:00Z`,
        counterparty_ref: counterpartyRef.trim() || null,
        counterparty_country: counterpartyCountry.trim() || null,
        is_cash: isCash,
      },
      {
        onSuccess: (txn) => {
          setAdded((prev) => [...prev, txn]);
          setJustAdded(txn);
        },
      },
    );
  }

  if (justAdded) {
    return (
      <div className="flex flex-col gap-3">
        <h2 className="font-ui text-sm font-semibold text-ink">Step 3 — Transactions</h2>
        <div className="rounded-sm border border-verified bg-verified-bg px-3 py-2 font-ui text-xs text-verified">
          Added {justAdded.txn_ref}: {justAdded.direction} {justAdded.amount} {justAdded.currency} via {justAdded.channel}
        </div>

        <TransactionLedger transactions={added} />

        <div className="mt-1 flex gap-2">
          <button
            onClick={() => {
              resetForm();
              setJustAdded(null);
            }}
            className="rounded-sm border border-rule bg-paper px-3 py-1.5 font-ui text-xs font-medium text-ink hover:bg-canvas"
          >
            Add another transaction
          </button>
          <button
            onClick={onDone}
            className="rounded-sm border border-ink bg-ink px-3 py-1.5 font-ui text-xs font-medium text-paper"
          >
            Done — {added.length} transaction{added.length === 1 ? "" : "s"} added
          </button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <h2 className="font-ui text-sm font-semibold text-ink">Step 3 — Transactions</h2>
      <p className="font-ui text-2xs text-ink-faint">For account {account.account_ref}</p>

      {added.length > 0 && <TransactionLedger transactions={added} />}

      <div className="grid grid-cols-2 gap-3">
        <Field label="Amount">
          <TextInput type="number" required min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <Field label="Currency">
          <TextInput required minLength={3} maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Direction">
          <Select value={direction} onChange={(e) => setDirection(e.target.value as typeof direction)}>
            <option value="credit">credit</option>
            <option value="debit">debit</option>
          </Select>
        </Field>
        <Field label="Channel">
          <Select value={channel} onChange={(e) => setChannel(e.target.value as typeof channel)}>
            <option value="cash">cash</option>
            <option value="wire">wire</option>
            <option value="ach">ach</option>
            <option value="card">card</option>
            <option value="check">check</option>
          </Select>
        </Field>
      </div>

      <Field label="Executed at (UTC)">
        <TextInput
          type="datetime-local"
          required
          max={nowUtcForInput()}
          value={executedAt}
          onChange={(e) => setExecutedAt(e.target.value)}
        />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Counterparty ref (optional)">
          <TextInput value={counterpartyRef} onChange={(e) => setCounterpartyRef(e.target.value)} />
        </Field>
        <Field label="Counterparty country (optional)">
          <TextInput
            maxLength={2}
            value={counterpartyCountry}
            onChange={(e) => setCounterpartyCountry(e.target.value.toUpperCase())}
          />
        </Field>
      </div>

      <label className="flex items-center gap-2 font-ui text-xs text-ink-muted">
        <input type="checkbox" checked={isCash} onChange={(e) => setIsCash(e.target.checked)} />
        Cash transaction
      </label>

      {createTransaction.isError && (
        <p className="font-ui text-xs text-critical">
          {createTransaction.error instanceof ApiError ? createTransaction.error.message : "Could not reach the backend."}
        </p>
      )}

      <div className="mt-1 flex gap-2">
        <button
          type="submit"
          disabled={createTransaction.isPending}
          className="self-start rounded-sm border border-ink bg-ink px-3 py-1.5 font-ui text-xs font-medium text-paper disabled:opacity-50"
        >
          {createTransaction.isPending ? "Adding…" : "Add transaction"}
        </button>
        {added.length > 0 && (
          <button
            type="button"
            onClick={onDone}
            className="rounded-sm border border-rule bg-paper px-3 py-1.5 font-ui text-xs font-medium text-ink hover:bg-canvas"
          >
            Done — {added.length} transaction{added.length === 1 ? "" : "s"} added
          </button>
        )}
      </div>
    </form>
  );
}

function TransactionLedger({ transactions }: { transactions: TransactionRecord[] }) {
  return (
    <ul className="flex flex-col gap-1 rounded-sm border border-rule bg-canvas p-2">
      {transactions.map((t) => (
        <li key={t.id} className="flex justify-between font-data text-2xs text-ink-muted">
          <span>{t.txn_ref}</span>
          <span>
            {t.direction} {t.amount} {t.currency} · {t.channel}
          </span>
        </li>
      ))}
    </ul>
  );
}

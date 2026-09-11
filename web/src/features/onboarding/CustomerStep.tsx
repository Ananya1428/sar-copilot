import { useState } from "react";

import { useCreateCustomer } from "@/api/hooks";
import { ApiError } from "@/api/client";
import type { CustomerRecord } from "@/api/types";

import { Field, Select, TextInput } from "./Field";

const today = new Date().toISOString().slice(0, 10);

export function CustomerStep({ onCreated }: { onCreated: (customer: CustomerRecord) => void }) {
  const [legalName, setLegalName] = useState("");
  const [entityType, setEntityType] = useState<"individual" | "business">("individual");
  const [onboardedAt, setOnboardedAt] = useState(today);
  const [riskRating, setRiskRating] = useState<"LOW" | "MEDIUM" | "HIGH">("LOW");
  const [occupation, setOccupation] = useState("");
  const [country, setCountry] = useState("US");

  const createCustomer = useCreateCustomer();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    createCustomer.mutate(
      {
        legal_name: legalName,
        entity_type: entityType,
        onboarded_at: onboardedAt,
        risk_rating: riskRating,
        occupation: occupation.trim() || null,
        country,
      },
      { onSuccess: onCreated },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <h2 className="font-ui text-sm font-semibold text-ink">Step 1 — Customer</h2>

      <Field label="Legal name">
        <TextInput required minLength={1} value={legalName} onChange={(e) => setLegalName(e.target.value)} />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Entity type">
          <Select value={entityType} onChange={(e) => setEntityType(e.target.value as typeof entityType)}>
            <option value="individual">individual</option>
            <option value="business">business</option>
          </Select>
        </Field>
        <Field label="Risk rating">
          <Select value={riskRating} onChange={(e) => setRiskRating(e.target.value as typeof riskRating)}>
            <option value="LOW">LOW</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="HIGH">HIGH</option>
          </Select>
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Onboarded at">
          <TextInput type="date" required max={today} value={onboardedAt} onChange={(e) => setOnboardedAt(e.target.value)} />
        </Field>
        <Field label="Country (ISO-2)">
          <TextInput
            required
            minLength={2}
            maxLength={2}
            pattern="[A-Za-z]{2}"
            value={country}
            onChange={(e) => setCountry(e.target.value.toUpperCase())}
          />
        </Field>
      </div>

      <Field label="Occupation (optional)">
        <TextInput value={occupation} onChange={(e) => setOccupation(e.target.value)} />
      </Field>

      {createCustomer.isError && (
        <p className="font-ui text-xs text-critical">
          {createCustomer.error instanceof ApiError ? createCustomer.error.message : "Could not reach the backend."}
        </p>
      )}

      <button
        type="submit"
        disabled={createCustomer.isPending}
        className="mt-1 self-start rounded-sm border border-ink bg-ink px-3 py-1.5 font-ui text-xs font-medium text-paper disabled:opacity-50"
      >
        {createCustomer.isPending ? "Creating…" : "Create customer →"}
      </button>
    </form>
  );
}

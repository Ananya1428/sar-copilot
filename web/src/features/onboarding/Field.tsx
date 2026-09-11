import type { ReactNode } from "react";

const inputClass =
  "rounded-sm border border-rule bg-paper px-2.5 py-1.5 font-ui text-sm text-ink placeholder:text-ink-faint focus-visible:border-trace disabled:opacity-50";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-ui text-2xs uppercase tracking-wide text-ink-faint">{label}</span>
      {children}
    </label>
  );
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputClass} ${props.className ?? ""}`} />;
}

export function Select({ children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={`${inputClass} ${props.className ?? ""}`}>
      {children}
    </select>
  );
}

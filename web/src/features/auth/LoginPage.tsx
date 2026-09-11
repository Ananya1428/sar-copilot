import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useLogin } from "@/api/hooks";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/stores/authStore";

/** api/app/cli.py DEMO_USERS — local-only, throwaway demo accounts seeded
 * by `python -m app.cli seed`. Never real credentials; shown here so a
 * reviewer trying this out has something to log in with. */
const DEMO_USERS = [
  { email: "analyst@sarcopilot.local", password: "analyst-demo-123", role: "analyst" },
  { email: "reviewer@sarcopilot.local", password: "reviewer-demo-123", role: "reviewer" },
  { email: "officer@sarcopilot.local", password: "officer-demo-123", role: "officer" },
  { email: "admin@sarcopilot.local", password: "admin-demo-123", role: "admin" },
];

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();
  const setAuth = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    login.mutate(
      { email, password },
      {
        onSuccess: (tokens) => {
          setAuth(tokens.access_token, tokens.refresh_token, email);
          navigate("/", { replace: true });
        },
      },
    );
  }

  // The backend deliberately returns the same 401 message for "wrong
  // password" and "unknown email" (auth.py's login() docstring — an
  // enumeration-safe design). Just surfacing the real backend message
  // preserves that; nothing here re-derives or narrows which one it was.
  const errorMessage = login.isError
    ? login.error instanceof ApiError
      ? login.error.message
      : "Could not reach the backend."
    : null;

  return (
    <div className="flex min-h-full items-center justify-center bg-canvas px-4">
      <div className="w-full max-w-sm rounded-md border border-rule bg-panel p-6">
        <h1 className="font-ui text-lg font-semibold text-ink">SAR Copilot</h1>
        <p className="mt-0.5 font-ui text-xs text-ink-muted">Sign in to continue</p>

        <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="font-ui text-2xs uppercase tracking-wide text-ink-faint">Email</span>
            <input
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-sm border border-rule bg-paper px-2.5 py-1.5 font-ui text-sm text-ink placeholder:text-ink-faint focus-visible:border-trace"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="font-ui text-2xs uppercase tracking-wide text-ink-faint">Password</span>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-sm border border-rule bg-paper px-2.5 py-1.5 font-ui text-sm text-ink placeholder:text-ink-faint focus-visible:border-trace"
            />
          </label>

          {errorMessage && <p className="font-ui text-xs text-critical">{errorMessage}</p>}

          <button
            type="submit"
            disabled={login.isPending}
            className="mt-1 rounded-sm border border-ink bg-ink px-3 py-1.5 font-ui text-xs font-medium text-paper disabled:opacity-50"
          >
            {login.isPending ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <details className="mt-5 border-t border-rule pt-3">
          <summary className="cursor-pointer select-none font-ui text-2xs uppercase tracking-wide text-ink-faint">
            Local demo accounts
          </summary>
          <div className="mt-2 flex flex-col gap-1.5">
            {DEMO_USERS.map((u) => (
              <button
                key={u.email}
                type="button"
                onClick={() => {
                  setEmail(u.email);
                  setPassword(u.password);
                }}
                className="flex items-center justify-between rounded-sm border border-rule bg-paper px-2 py-1 font-data text-2xs text-ink-muted hover:bg-canvas"
              >
                <span>{u.email}</span>
                <span className="text-ink-faint">{u.role}</span>
              </button>
            ))}
            <p className="mt-1 font-ui text-2xs text-ink-faint">
              Local-only demo credentials seeded by the CLI — never real accounts, never for production use.
            </p>
          </div>
        </details>
      </div>
    </div>
  );
}

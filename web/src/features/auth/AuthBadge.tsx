import { useNavigate } from "react-router-dom";

import { useAuthStore } from "@/stores/authStore";

/**
 * Persistent "logged in as X (role)" indicator + logout, dropped into
 * every existing page's own header (this app never grew a shared layout
 * shell — see App.tsx — so each header gets this the same way each
 * already gets its own back-link/title)."
 */
export function AuthBadge() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  if (!user) return null;

  return (
    <div className="flex items-center gap-2 font-ui text-2xs text-ink-faint">
      <span>
        {user.email} <span className="text-ink-muted">({user.role})</span>
      </span>
      <button
        onClick={() => {
          logout();
          navigate("/login", { replace: true });
        }}
        className="rounded-sm border border-rule bg-paper px-2 py-1 font-ui text-2xs font-medium text-ink-muted hover:bg-canvas hover:text-ink"
      >
        Log out
      </button>
    </div>
  );
}

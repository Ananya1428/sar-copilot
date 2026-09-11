import { create } from "zustand";
import { persist } from "zustand/middleware";

import { decodeJwtPayload } from "@/lib/jwt";

export interface AuthUser {
  email: string;
  role: string;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  /** email is captured from the login form, not the token (the JWT only
   * carries `sub`/`role` — see api/app/domain/auth/security.py's
   * _create_token — no /me endpoint exists to look email back up from a
   * user id, and adding one is out of this part's scope). */
  login: (accessToken: string, refreshToken: string, email: string) => void;
  logout: () => void;
}

/**
 * SECURITY NOTE (flagged for LIMITATIONS.md, per the Part 8c brief): the
 * JWT is persisted to localStorage so a page refresh doesn't log the user
 * out. localStorage is readable by any script running on the page, so a
 * successful XSS anywhere in the app would be able to steal this token —
 * an httpOnly cookie set by the server would not be readable that way.
 * Acceptable for a local, single-user demo project; a real deployment
 * should move to httpOnly cookie-based sessions instead.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      login: (accessToken, refreshToken, email) => {
        const payload = decodeJwtPayload(accessToken);
        set({
          accessToken,
          refreshToken,
          user: { email, role: payload?.role ?? "unknown" },
        });
      },
      logout: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    { name: "sar-copilot-auth" },
  ),
);

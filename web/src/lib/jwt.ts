/**
 * Minimal JWT payload decode — no signature verification (the browser has
 * no way to verify a signature it can't keep the secret for, and doesn't
 * need to: the backend re-validates every request anyway per Part 8a's
 * get_current_user()). This is purely for reading `role`/`exp` out of a
 * token the backend already issued, so the UI can show "logged in as X
 * (role)" without a dedicated /me endpoint.
 */
export interface JwtPayload {
  sub: string;
  role: string;
  type: "access" | "refresh";
  iat: number;
  exp: number;
}

export function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const [, payloadB64] = token.split(".");
    if (!payloadB64) return null;
    const normalized = payloadB64.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
    return JSON.parse(atob(padded)) as JwtPayload;
  } catch {
    return null;
  }
}

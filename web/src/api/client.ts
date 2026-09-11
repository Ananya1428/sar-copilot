/**
 * Thin fetch wrapper over the FastAPI backend. Talks to nginx's /api/*
 * proxy (blueprint §21, wired up in Part 6c) by default; VITE_API_BASE_URL
 * overrides this for local `vite dev` against the API container directly.
 */
import { useAuthStore } from "@/stores/authStore";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

/** FastAPI's own 422 body shape ({"detail": [{"loc", "msg", "type"}, ...]})
 * is NOT a plain string like every hand-written 4xx in this backend uses
 * ({"detail": "case not found"}) — so extracting a human-readable message
 * has to handle both, or a validation error renders as "[object Object]". */
function extractDetailMessage(body: unknown): string | undefined {
  if (typeof body !== "object" || body === null || !("detail" in body)) return undefined;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "object" && item !== null && "msg" in item) {
          const loc = "loc" in item && Array.isArray((item as { loc: unknown }).loc) ? (item as { loc: unknown[] }).loc.join(".") : undefined;
          return loc ? `${loc}: ${(item as { msg: unknown }).msg}` : String((item as { msg: unknown }).msg);
        }
        return String(item);
      })
      .join("; ");
  }
  return undefined;
}

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(extractDetailMessage(body) ?? `request failed with status ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { accessToken } = useAuthStore.getState();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...init?.headers,
    },
  });

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      // non-JSON error body — leave `body` as null
    }

    // A 401 on a request that DID carry a token means the session is no
    // longer valid (expired/revoked) — a global "log out and go to
    // /login" is the right response, so no individual component has to
    // handle session expiry itself. A 401 on an unauthenticated request
    // (e.g. POST /auth/login with a wrong password) is the normal
    // login-form error path instead, so it must NOT trigger this —
    // distinguishing the two by "was a token attached" rather than by
    // URL keeps this logic in one place without special-casing routes.
    if (res.status === 401 && accessToken) {
      useAuthStore.getState().logout();
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }

    throw new ApiError(res.status, body);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
};

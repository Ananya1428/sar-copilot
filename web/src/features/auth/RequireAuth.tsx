import { Navigate, Outlet } from "react-router-dom";

import { useAuthStore } from "@/stores/authStore";

/**
 * Route guard (Part 8c) — every existing screen (Case Queue, Case
 * Workspace, ...) sits behind this. No valid token -> redirect to /login.
 * Reactive: if `accessToken` is cleared anywhere (logout, or the API
 * client's global 401 handler), this re-renders and redirects on its own
 * — no page needs to check auth itself.
 */
export function RequireAuth() {
  const accessToken = useAuthStore((s) => s.accessToken);
  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}

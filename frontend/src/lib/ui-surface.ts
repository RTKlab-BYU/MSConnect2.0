import type { CurrentUser } from "@/lib/api/types";

export type SurfaceRole = CurrentUser["global_role"] | null | undefined;

export function isOperatorRole(role: SurfaceRole): boolean {
  return role === "admin" || role === "pi";
}

export function isAdminRole(role: SurfaceRole): boolean {
  return role === "admin";
}

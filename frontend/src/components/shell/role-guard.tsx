import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { RouteFallback } from "@/components/shell/route-fallback";
import { fetchCurrentUser, queryKeys } from "@/lib/api/queries";

type Role = "admin" | "pi" | "researcher" | "collaborator";

export function RoleGuard({ allow, allowFacilityManager = false, children }: { allow: Role[]; allowFacilityManager?: boolean; children: ReactNode }) {
  const location = useLocation();
  const currentUserQuery = useQuery({
    queryKey: queryKeys.currentUser(),
    queryFn: fetchCurrentUser,
  });

  if (currentUserQuery.isLoading) {
    return <RouteFallback label="Checking access" />;
  }

  const role = currentUserQuery.data?.global_role;
  const superuserAllowed = Boolean(currentUserQuery.data?.is_superuser && allow.includes("admin"));
  const facilityManagerAllowed = Boolean(allowFacilityManager && currentUserQuery.data?.labs.some((lab) => lab.role === "facility_manager" || lab.role === "admin"));
  if ((!role || !allow.includes(role)) && !superuserAllowed && !facilityManagerAllowed) {
    return <Navigate to="/dashboard" replace state={{ from: location.pathname }} />;
  }

  return children;
}

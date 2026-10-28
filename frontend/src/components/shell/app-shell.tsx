import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, ClipboardList, FlaskConical, LogOut, Microscope, Search, Settings2, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { CommandPalette } from "@/components/shell/command-palette";
import { Button } from "@/components/ui/button";
import { fetchCurrentUser, queryKeys, resendMyVerification } from "@/lib/api/queries";
import { csrfToken } from "@/lib/api/client";
import { isFacilityProfile } from "@/lib/instance-profile";
import { isOperatorRole } from "@/lib/ui-surface";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/ui-store";

const primaryItems = [
  { to: "/projects", label: "Projects", icon: FlaskConical },
  { to: "/qc/hye", label: "Quality control", icon: Microscope },
  { to: "/monitoring", label: "Live status", icon: Activity, operatorOnly: true },
  { to: "/settings", label: "Operations", icon: Settings2, adminOnly: true },
  { to: "/admin/users", label: "Administration", icon: Users, adminOnly: true },
];

const facilityItems = [
  { to: "/submissions", label: "Submissions", icon: ClipboardList },
  { to: "/intake", label: "Intake queue", icon: ClipboardList, operatorOnly: true },
];

export function AppShell() {
  const setCommandOpen = useUiStore((state) => state.setCommandOpen);
  const currentUserQuery = useQuery({ queryKey: queryKeys.currentUser(), queryFn: fetchCurrentUser });
  const queryClient = useQueryClient();
  const currentUser = currentUserQuery.data;
  const [logoutError, setLogoutError] = useState("");
  const location = useLocation();
  const operator = isOperatorRole(currentUser?.global_role) || Boolean(currentUser?.is_superuser);
  const admin = currentUser?.global_role === "admin" || Boolean(currentUser?.is_superuser);
  const verificationMutation = useMutation({
    mutationFn: resendMyVerification,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.currentUser() }),
  });
  const items = [
    ...primaryItems.filter((item) => (!item.operatorOnly || operator) && (!item.adminOnly || admin)),
    ...(isFacilityProfile ? facilityItems.filter((item) => !item.operatorOnly || operator) : []),
  ];

  async function signOut() {
    setLogoutError("");
    try {
      const response = await fetch("/accounts/logout/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfToken(), Accept: "text/html" },
      });
      if (!response.ok) throw new Error("Sign out failed. Please try again.");
      window.location.assign("/accounts/login/");
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : "Sign out failed.");
    }
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setCommandOpen]);

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b border-border/60 bg-background">
        <div className="mx-auto flex h-14 max-w-[1560px] items-center gap-3 px-4 md:px-6">
          <Link to="/dashboard" aria-label="MSConnect dashboard" className="flex min-w-0 max-w-[42vw] items-center gap-2.5 rounded-md text-foreground no-underline hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 sm:max-w-[15rem]">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-xs font-black text-primary-foreground">MS</span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold leading-tight">MSConnect</span>
              <span className="block truncate text-[11px] text-muted-foreground">{currentUser?.instance_label ?? "Research workspace"}</span>
            </span>
          </Link>
          <Button variant="secondary" className="ml-auto hidden h-9 min-w-[220px] justify-start text-muted-foreground sm:flex" onClick={() => setCommandOpen(true)}>
            <Search className="h-4 w-4" /> Search projects
            <span className="ml-auto rounded-sm bg-muted px-1.5 py-0.5 font-mono text-[10px]">⌘K</span>
          </Button>
          <Button variant="ghost" size="icon" className="sm:hidden" aria-label="Search projects" onClick={() => setCommandOpen(true)}><Search className="h-4 w-4" /></Button>
          <div className="hidden max-w-44 truncate text-xs text-muted-foreground md:block" title={currentUser?.email}>{currentUser?.username ?? "Account"}</div>
          <Button variant="ghost" size="sm" onClick={signOut} aria-label="Log out" title="Log out"><LogOut className="h-4 w-4" /><span className="hidden sm:inline">Log out</span></Button>
        </div>
        {currentUser && !currentUser.email_verified_at ? (
          <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 border-t border-warning/40 bg-card px-4 py-2 text-xs text-foreground" role="status" aria-live="polite">
            <span>Email not verified. Check {currentUser.email || "your inbox"}.</span>
            <button className="font-semibold underline underline-offset-2 disabled:opacity-60" disabled={verificationMutation.isPending} onClick={() => verificationMutation.mutate()}>
              {verificationMutation.isPending ? "Sending…" : "Resend verification email"}
            </button>
            {verificationMutation.isError ? <span role="alert">{verificationMutation.error.message}</span> : null}
            {verificationMutation.isSuccess && !verificationMutation.data.already_verified ? <span>Email sent. Check your inbox and spam folder.</span> : null}
          </div>
        ) : null}
      </header>
      <div className="mx-auto grid min-h-[calc(100vh-3.5rem)] max-w-[1560px] md:grid-cols-[204px_minmax(0,1fr)]">
        <aside className="bg-secondary p-3 md:p-4">
          <div className="flex gap-1 overflow-x-auto md:grid md:content-start md:gap-1.5">
            {items.map((item) => {
              const active = item.to === "/qc/hye" ? location.pathname.startsWith("/qc") : undefined;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => cn(
                    "flex h-10 shrink-0 items-center gap-2 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground md:w-full",
                    (active ?? isActive) && "bg-secondary font-semibold text-foreground",
                  )}
                >
                  <item.icon aria-hidden="true" className="h-4 w-4 shrink-0" />{item.label}
                </NavLink>
              );
            })}
          </div>
        </aside>
        <a href="#main-content" className="sr-only rounded-sm bg-background p-2 focus:not-sr-only focus:absolute focus:left-4 focus:top-16 focus:z-50">Skip to content</a>
        <main id="main-content" className="min-w-0 p-4 md:p-6" tabIndex={-1}>
          {logoutError ? <div role="alert" className="mb-4 text-sm text-destructive">{logoutError}</div> : null}
          <Outlet />
        </main>
      </div>
      <CommandPalette />
    </div>
  );
}

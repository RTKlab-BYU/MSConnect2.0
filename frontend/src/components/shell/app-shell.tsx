import { useQuery } from "@tanstack/react-query";
import { FlaskConical, LayoutDashboard, Moon, Search, Sun } from "lucide-react";
import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { CommandPalette } from "@/components/shell/command-palette";
import { fetchCurrentUser, queryKeys } from "@/lib/api/queries";
import { isOperatorRole } from "@/lib/ui-surface";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/ui-store";

const collaboratorNavItems = [
  { to: "/projects", label: "Projects", icon: FlaskConical },
];

const operatorNavItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/projects", label: "Projects", icon: FlaskConical },
  { to: "/monitoring", label: "Monitoring", icon: Search },
];

export function AppShell() {
  const theme = useUiStore((state) => state.theme);
  const setTheme = useUiStore((state) => state.setTheme);
  const setCommandOpen = useUiStore((state) => state.setCommandOpen);
  const currentUserQuery = useQuery({
    queryKey: queryKeys.currentUser(),
    queryFn: fetchCurrentUser,
  });
  const currentUser = currentUserQuery.data;
  const navItems = isOperatorRole(currentUser?.global_role) ? operatorNavItems : collaboratorNavItems;

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
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center gap-3 px-4 md:px-6">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary font-mono text-xs font-black text-primary-foreground">
            MS
          </div>
          <nav className="flex items-center gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "flex h-9 items-center gap-2 rounded-md px-3 text-sm font-bold text-muted-foreground hover:bg-secondary hover:text-foreground",
                    isActive && "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
          </nav>
          {currentUser?.email_verified_at ? null : (
            <div className="hidden rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-950 md:block">
              Email verification pending
            </div>
          )}
          <Button variant="secondary" className="ml-auto hidden min-w-[240px] justify-start rounded-md text-muted-foreground sm:flex" onClick={() => setCommandOpen(true)}>
            <Search className="h-4 w-4" />
            Search projects
            <span className="ml-auto rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">⌘K</span>
          </Button>
          <Button variant="ghost" size="icon" className="sm:hidden" aria-label="Search projects" onClick={() => setCommandOpen(true)}>
            <Search className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Toggle color theme"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-[1500px] p-4 md:p-6">
        <Outlet />
      </main>
      <CommandPalette />
    </div>
  );
}

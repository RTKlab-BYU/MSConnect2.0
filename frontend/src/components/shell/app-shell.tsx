import { Activity, CheckCircle2, HardDrive, Moon, Search, Settings, Sun, TestTube2, UploadCloud } from "lucide-react";
import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { CommandPalette } from "@/components/shell/command-palette";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/ui-store";

const navItems = [
  { to: "/projects", label: "Projects", icon: TestTube2 },
  { to: "/qc", label: "QC", icon: CheckCircle2 },
  { to: "/monitoring", label: "Monitoring", icon: Activity },
  { to: "/processing", label: "Processing", icon: HardDrive },
  { to: "/uploads", label: "Uploads", icon: UploadCloud },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell() {
  const theme = useUiStore((state) => state.theme);
  const setTheme = useUiStore((state) => state.setTheme);
  const setCommandOpen = useUiStore((state) => state.setCommandOpen);

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
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r bg-card xl:block">
        <div className="flex h-14 items-center border-b px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary font-mono text-xs font-black text-primary-foreground">
            MS
          </div>
          <div className="ml-3">
            <div className="text-sm font-bold leading-none">MSConnect</div>
            <div className="mt-1 text-xs font-semibold text-muted-foreground">LIMS / SDMS</div>
          </div>
        </div>
        <nav className="grid gap-1 p-3">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold text-muted-foreground hover:bg-secondary hover:text-foreground",
                  isActive && "bg-secondary text-foreground",
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="xl:pl-64">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-background/95 px-4 backdrop-blur">
          <Button variant="secondary" className="min-w-[280px] justify-start text-muted-foreground" onClick={() => setCommandOpen(true)}>
            <Search className="h-4 w-4" />
            Search records
            <span className="ml-auto rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">⌘K</span>
          </Button>
          <div className="ml-auto flex items-center gap-2">
            <a className="text-sm font-semibold text-muted-foreground" href="/ui/projects">
              Legacy UI
            </a>
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
        <main className="mx-auto max-w-[1600px] p-4">
          <Outlet />
        </main>
      </div>
      <CommandPalette />
    </div>
  );
}

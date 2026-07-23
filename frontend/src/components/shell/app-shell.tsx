import { Activity, BarChart3, CheckCircle2, HardDrive, Moon, Search, Settings, Sun, TestTube2, UploadCloud } from "lucide-react";
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
  { to: "/spectra", label: "Spectra", icon: BarChart3 },
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
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r bg-card/88 shadow-[18px_0_60px_rgb(15_23_42/0.06)] backdrop-blur xl:block">
        <div className="flex h-16 items-center border-b px-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary font-mono text-xs font-black text-primary-foreground">
            MS
          </div>
          <div className="ml-3 text-sm font-black leading-none tracking-tight">MSConnect</div>
        </div>
        <nav className="grid gap-1.5 p-4">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-bold text-muted-foreground hover:bg-secondary hover:text-foreground",
                  isActive && "bg-primary text-primary-foreground shadow-sm hover:bg-primary hover:text-primary-foreground",
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
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur">
          <Button variant="secondary" className="min-w-[280px] justify-start rounded-2xl text-muted-foreground" onClick={() => setCommandOpen(true)}>
            <Search className="h-4 w-4" />
            Search records
            <span className="ml-auto rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">⌘K</span>
          </Button>
          <div className="ml-auto flex items-center gap-2">
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
      </div>
      <CommandPalette />
    </div>
  );
}

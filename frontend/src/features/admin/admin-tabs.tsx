import { NavLink } from "react-router-dom";

const sections = [
  { to: "/admin/users", label: "Users" },
  { to: "/admin/labs", label: "Labs" },
  { to: "/admin/lc-ms", label: "LC-MS setups" },
  { to: "/admin/settings", label: "Global settings" },
  { to: "/processing/admin?type=processor", label: "Nodes & compute" },
  { to: "/admin/assistant", label: "AI agent" },
];

export function AdminTabs() {
  return (
    <nav aria-label="Administration sections" className="flex max-w-full gap-1 overflow-x-auto">
      {sections.map((section) => (
        <NavLink
          key={section.to}
          to={section.to}
          className={({ isActive }) => `shrink-0 px-3 py-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${isActive ? "bg-secondary font-semibold text-foreground" : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground"}`}
        >
          {section.label}
        </NavLink>
      ))}
    </nav>
  );
}

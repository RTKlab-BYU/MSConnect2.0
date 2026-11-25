import { ArrowLeft, FlaskConical, UsersRound } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import AdminLabsPage from "@/features/admin/labs-page";
import AdminUserAccessPage from "@/features/admin/user-access-page";
import { AdminTabs } from "@/features/admin/admin-tabs";

export default function AdminSetupPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const view = searchParams.get("view");
  const setView = (next: string) => setSearchParams(next ? { view: next } : {});

  return <div className="mx-auto grid w-full max-w-6xl gap-5">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Administration</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Users & labs</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">Set up lab records and account access in one place.</p>
      </div>
      {view ? <Button variant="secondary" onClick={() => setView("")}><ArrowLeft className="h-4 w-4" />Back to setup</Button> : null}
    </header>
    <AdminTabs />
    {!view ? <div className="grid gap-3 md:grid-cols-2">
      <button type="button" onClick={() => setView("users")} className="flex items-center gap-4 border bg-card p-5 text-left hover:bg-secondary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <UsersRound className="h-5 w-5 shrink-0 text-primary" />
        <span><span className="block font-semibold">Users</span><span className="mt-1 block text-sm text-muted-foreground">Create accounts, share setup links, and manage lab access.</span></span>
      </button>
      <button type="button" onClick={() => setView("labs")} className="flex items-center gap-4 border bg-card p-5 text-left hover:bg-secondary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <FlaskConical className="h-5 w-5 shrink-0 text-primary" />
        <span><span className="block font-semibold">Labs</span><span className="mt-1 block text-sm text-muted-foreground">Add universities, facilities, and labs before setting up users.</span></span>
      </button>
      <div className="border bg-secondary/20 p-4 text-sm text-muted-foreground md:col-span-2">Typical setup: create the university, facility, and lab; then create each user and share their account setup link.</div>
    </div> : <section aria-label={view === "users" ? "User setup" : "Lab setup"}>
      {view === "users" ? <AdminUserAccessPage embedded /> : <AdminLabsPage embedded />}
    </section>}
    <div className="text-xs text-muted-foreground"><Link to="/admin" className="underline underline-offset-2">Administration overview</Link></div>
  </div>;
}

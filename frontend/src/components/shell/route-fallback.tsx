import { AlertTriangle, Home, Loader2 } from "lucide-react";
import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function RouteFallback({ label }: { label: string }) {
  return (
    <div className="flex h-64 items-center justify-center rounded-lg border bg-card text-sm text-muted-foreground">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}

export function RouteErrorBoundary() {
  const error = useRouteError();
  const isNotFound = isRouteErrorResponse(error) && error.status === 404;

  return (
    <div className="min-h-screen bg-background p-4 text-foreground">
      <div className="mx-auto grid min-h-[calc(100vh-2rem)] max-w-5xl place-items-center">
        <section className="relative w-full overflow-hidden rounded-3xl border bg-card p-8 shadow-lg md:p-12">
          <div className="absolute right-[-6rem] top-[-6rem] h-64 w-64 rounded-full bg-accent/10" />
          <div className="absolute bottom-[-8rem] left-[-5rem] h-72 w-72 rounded-full bg-primary/10" />
          <div className="relative max-w-2xl">
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-warning/15 text-warning">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <p className="text-xs font-black uppercase tracking-[0.22em] text-muted-foreground">
              {isNotFound ? "Route not found" : "Application error"}
            </p>
            <h1 className="mt-3 text-4xl font-black tracking-tight md:text-5xl">
              {isNotFound ? "That workspace page does not exist." : "MSConnect hit an unexpected state."}
            </h1>
            <p className="mt-4 max-w-xl text-sm leading-6 text-muted-foreground">
              {isNotFound
                ? "The URL does not map to an active MSConnect workspace. Use the project dashboard to continue."
                : "The shell stayed online, but this route failed while rendering. Return to the dashboard and try again."}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link to="/projects">
                  <Home className="h-4 w-4" />
                  Open projects
                </Link>
              </Button>
              <Button asChild variant="secondary" size="lg">
                <a href="/accounts/logout/">Sign out</a>
              </Button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

export function NotFoundRoute() {
  return (
    <section className="overflow-hidden rounded-3xl border bg-card p-8 shadow-md">
      <div className="max-w-2xl">
        <p className="text-xs font-black uppercase tracking-[0.22em] text-muted-foreground">Route not found</p>
        <h1 className="mt-3 text-3xl font-black tracking-tight">This MSConnect page is not available.</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          The URL may be outdated, misspelled, or from an older interface route. Continue from the project dashboard.
        </p>
        <Button asChild className="mt-6">
          <Link to="/projects">
            <Home className="h-4 w-4" />
            Open projects
          </Link>
        </Button>
      </div>
    </section>
  );
}

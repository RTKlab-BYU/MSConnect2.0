import { ExternalLink } from "lucide-react";

import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Settings" }]} />
      <section className="rounded-lg border bg-card p-4 shadow-sm">
        <p className="text-xs font-bold uppercase text-muted-foreground">Administration</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          Phase 1 keeps authoritative user, instrument, protocol, and pipeline editing in Django admin while React read models come online.
        </p>
      </section>
      <div className="grid gap-4 lg:grid-cols-3">
        {[
          ["Users and Labs", "Manage users, lab membership, PI/admin scope, and facility access."],
          ["Instruments", "Maintain LC/MS instruments and instrument configurations."],
          ["Pipelines", "Register processing pipelines, versions, containers, and node settings."],
        ].map(([title, description]) => (
          <Card key={title}>
            <CardHeader>
              <CardTitle>{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="secondary">
                <a href="/admin/">
                  Open Django admin
                  <ExternalLink className="h-4 w-4" />
                </a>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

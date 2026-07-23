import { ExternalLink } from "lucide-react";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Settings" }]} />
      <PageHero
        eyebrow="Administration"
        title="Settings"
        description="Manage the operational configuration around users, labs, instruments, pipelines, storage, and agents."
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {[
          ["Users and Labs", "Manage users, lab membership, PI/admin scope, and facility access."],
          ["Instruments", "Maintain LC/MS instruments and instrument configurations."],
          ["Pipelines", "Register processing pipelines, versions, containers, and node settings."],
          ["Storage", "Review raw-file storage, result paths, and object-storage adapters."],
          ["Agents", "Inspect watcher and processor agent configuration."],
          ["Security", "Review account access and session settings."],
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

import { useQuery } from "@tanstack/react-query";
import { Bot, ExternalLink, KeyRound } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { AdminTabs } from "@/features/admin/admin-tabs";
import { fetchAdminRuntimeSettings, queryKeys } from "@/lib/api/queries";

export default function AdminAssistantPage() {
  const runtimeQuery = useQuery({ queryKey: queryKeys.adminRuntimeSettings(), queryFn: fetchAdminRuntimeSettings });
  const assistant = runtimeQuery.data?.assistant;
  const models = assistant?.models ?? [];
  const providerNames = Object.keys(assistant?.providers ?? {});
  const activeProviders = providerNames.filter((provider) => assistant?.providers[provider]?.configured);

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "AI agent" }]} />
      <PageHero eyebrow="Administration" title="AI agent" description="Inspect which assistant providers and models are actually enabled. Credentials remain server-side and are never displayed here." />
      <AdminTabs />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Bot className="h-5 w-5" /> Provider status</CardTitle>
          <CardDescription>Project assistants use only the configured provider/model pairs shown below.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          {providerNames.map((provider) => (
            <div key={provider} className="min-w-0 border border-border bg-card p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="min-w-0 break-words font-semibold capitalize">{provider}</h2>
                <StatusBadge status={assistant?.providers[provider]?.configured ? "complete" : "warning"} />
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{assistant?.providers[provider]?.configured ? "Credentials detected in the server environment." : "No credentials detected; assistant model selection will be unavailable."}</p>
            </div>
          ))}
          {!providerNames.length ? <p className="text-sm text-muted-foreground">{runtimeQuery.isLoading ? "Checking provider configuration…" : "Provider status unavailable."}</p> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Enabled models</CardTitle><CardDescription>Secrets are intentionally hidden; only provider and model identifiers are returned.</CardDescription></CardHeader>
        <CardContent className="grid gap-2">
          {models.map(({ provider, model }) => <div key={`${provider}:${model}`} className="flex min-w-0 flex-wrap items-center justify-between gap-2 border border-border px-3 py-2 text-sm"><span className="capitalize text-muted-foreground">{provider}</span><code className="max-w-full break-all">{model}</code></div>)}
          {!models.length ? <p className="border border-border px-3 py-3 text-sm text-muted-foreground">No AI models are currently enabled.</p> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><KeyRound className="h-4 w-4" /> Configure providers</CardTitle><CardDescription>Set provider credentials in the server’s private environment, then recreate the web service to load them.</CardDescription></CardHeader>
        <CardContent className="grid gap-3 text-sm text-muted-foreground">
          <p>Supported providers currently detected: {activeProviders.length ? activeProviders.join(", ") : "none"}. API keys must not be stored in project records or exposed through the browser.</p>
          <div className="flex flex-wrap gap-2"><Button asChild variant="secondary"><Link to="/admin/settings">Open global settings</Link></Button><Button asChild variant="ghost"><a href="/api/docs/" target="_blank" rel="noreferrer">API documentation <ExternalLink className="h-4 w-4" /></a></Button></div>
        </CardContent>
      </Card>
    </div>
  );
}

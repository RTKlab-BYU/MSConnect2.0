import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Save, Trash2 } from "lucide-react";
import { useState } from "react";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { AdminTabs } from "@/features/admin/admin-tabs";
import { fetchAdminRuntimeSettings, fetchAssistantCredentialStatus, queryKeys, saveAssistantCredential } from "@/lib/api/queries";

export default function AdminAssistantPage() {
  const queryClient = useQueryClient();
  const runtimeQuery = useQuery({ queryKey: queryKeys.adminRuntimeSettings(), queryFn: fetchAdminRuntimeSettings });
  const credentialQuery = useQuery({ queryKey: ["assistant-credential-status"], queryFn: fetchAssistantCredentialStatus });
  const [provider, setProvider] = useState<"openai" | "anthropic">("openai");
  const [apiKey, setApiKey] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const credentialMutation = useMutation({
    mutationFn: (payload: { provider: "openai" | "anthropic"; api_key?: string; clear?: boolean }) => saveAssistantCredential(payload),
    onSuccess: async (result) => {
      setApiKey("");
      setNotice(result.configured ? `${result.provider} credentials saved.` : `${result.provider} stored credentials cleared; server environment credentials may still be active.`);
      setError("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["assistant-credential-status"] }),
        queryClient.invalidateQueries({ queryKey: queryKeys.adminRuntimeSettings() }),
      ]);
    },
    onError: (reason) => { setError(reason instanceof Error ? reason.message : "Could not save AI credentials."); setNotice(""); },
  });
  const assistant = runtimeQuery.data?.assistant;
  const models = assistant?.models ?? [];
  const providers = ["openai", "anthropic"] as const;

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Administration", href: "/admin" }, { label: "AI assistant" }]} />
      <PageHero eyebrow="Administration" title="AI assistant" description="Add provider credentials and review the models available to project assistants." />
      <AdminTabs />
      {error ? <p role="alert" className="border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</p> : null}
      {notice ? <p role="status" className="border bg-secondary/40 p-3 text-sm">{notice}</p> : null}
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Bot className="h-5 w-5" /> Provider credentials</CardTitle><CardDescription>Keys are encrypted before they are stored. Existing server environment keys continue to work as a fallback.</CardDescription></CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-2">
          {providers.map((name) => {
            const configured = credentialQuery.data?.providers[name]?.configured ?? false;
            return <form key={name} className="grid content-start gap-3 border p-4" onSubmit={(event) => { event.preventDefault(); setProvider(name); credentialMutation.mutate({ provider: name, api_key: apiKey.trim() }); }}>
              <div className="flex items-center justify-between gap-3"><h2 className="font-semibold capitalize">{name}</h2><StatusBadge status={configured ? "complete" : "warning"} /></div>
              <p className="text-sm text-muted-foreground">{configured ? "A provider key is configured. The saved value is never shown." : "No key is configured yet."}</p>
              <label className="grid gap-1.5 text-sm font-medium">{configured ? "Replace API key" : "API key"}<Input type="password" autoComplete="new-password" value={provider === name ? apiKey : ""} onChange={(event) => { setProvider(name); setApiKey(event.target.value); }} placeholder={configured ? "Enter a new key to replace" : "Paste provider API key"} /></label>
              <div className="flex flex-wrap gap-2"><Button type="submit" disabled={!apiKey.trim() || credentialMutation.isPending}><Save className="h-4 w-4" />Save key</Button>{configured ? <Button type="button" variant="secondary" disabled={credentialMutation.isPending} onClick={() => credentialMutation.mutate({ provider: name, clear: true })}><Trash2 className="h-4 w-4" />Clear stored key</Button> : null}</div>
            </form>;
          })}
          {credentialQuery.isError ? <p role="alert" className="text-sm text-destructive md:col-span-2">Could not load credential status: {credentialQuery.error.message}</p> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Enabled models</CardTitle><CardDescription>Models come from the server’s configured provider model lists, such as MSCONNECT_ASSISTANT_OPENAI_MODELS. Only provider and model names are shown.</CardDescription></CardHeader>
        <CardContent className="grid gap-2">
          {models.map(({ provider, model }) => <div key={`${provider}:${model}`} className="flex min-w-0 flex-wrap items-center justify-between gap-2 border border-border px-3 py-2 text-sm"><span className="capitalize text-muted-foreground">{provider}</span><code className="max-w-full break-all">{model}</code></div>)}
          {!models.length ? <p className="border border-border px-3 py-3 text-sm text-muted-foreground">No AI models are currently enabled.</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}

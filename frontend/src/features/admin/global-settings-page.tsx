import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AdminTabs } from "@/features/admin/admin-tabs";
import {
  fetchAdminRuntimeSettings,
  fetchDeploymentSettings,
  fetchProcessingPipelines,
  queryKeys,
  sendNotificationTest,
  updateDeploymentSettings,
} from "@/lib/api/queries";

function objectValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="grid gap-1.5 text-sm font-medium"><span>{label}</span>{children}</label>;
}

export default function AdminGlobalSettingsPage() {
  const queryClient = useQueryClient();
  const runtimeQuery = useQuery({ queryKey: queryKeys.adminRuntimeSettings(), queryFn: fetchAdminRuntimeSettings });
  const deploymentQuery = useQuery({ queryKey: queryKeys.deploymentSettings(), queryFn: fetchDeploymentSettings });
  const pipelinesQuery = useQuery({ queryKey: queryKeys.processingPipelines({ page: 1, page_size: 500 }), queryFn: () => fetchProcessingPipelines({ page: 1, page_size: 500 }) });
  const [threads, setThreads] = useState("");
  const [tempPath, setTempPath] = useState("");
  const [prtcPipeline, setPrtcPipeline] = useState("");
  const [targetedPipeline, setTargetedPipeline] = useState("");
  const [primaryLabName, setPrimaryLabName] = useState("");
  const [recipients, setRecipients] = useState("");
  const [cooldown, setCooldown] = useState("3600");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const deployment = deploymentQuery.data;
  const metadata = objectValue(deployment?.metadata);
  const diann = objectValue(metadata.diann);
  const pipelines = useMemo(() => (pipelinesQuery.data?.results ?? []).filter((pipeline) => objectValue(pipeline.parameters).engine === "skyline" || pipeline.name.toLowerCase().includes("skyline")), [pipelinesQuery.data?.results]);

  useEffect(() => {
    const storedMetadata = objectValue(deployment?.metadata);
    const storedDiann = objectValue(storedMetadata.diann);
    const storedTags = objectValue(storedDiann.performance_tags ?? storedMetadata.diann_performance_tags);
    const storedNotifications = objectValue(storedMetadata.notifications);
    const storedIdentity = objectValue(storedMetadata.instance_identity);
    setThreads(storedTags.threads === undefined ? "" : String(storedTags.threads));
    setTempPath(storedTags.temp === undefined ? "" : String(storedTags.temp));
    setPrtcPipeline(deployment?.prtc_skyline_pipeline ? String(deployment.prtc_skyline_pipeline) : "");
    setTargetedPipeline(deployment?.targeted_skyline_pipeline ? String(deployment.targeted_skyline_pipeline) : "");
    setPrimaryLabName(String(storedIdentity.primary_lab_name ?? ""));
    setRecipients(Array.isArray(storedNotifications.recipients) ? storedNotifications.recipients.join(", ") : "");
    setCooldown(String(storedNotifications.cooldown_seconds ?? 3600));
  }, [deployment]);

  const saveMutation = useMutation({
    mutationFn: () => updateDeploymentSettings({
      prtc_skyline_pipeline: prtcPipeline ? Number(prtcPipeline) : null,
      targeted_skyline_pipeline: targetedPipeline ? Number(targetedPipeline) : null,
      metadata: {
        ...metadata,
        diann: { ...diann, performance_tags: { threads: threads.trim() || undefined, temp: tempPath.trim() || undefined } },
        instance_identity: { ...objectValue(metadata.instance_identity), primary_lab_name: primaryLabName.trim() },
        notifications: { recipients: recipients.split(",").map((email) => email.trim()).filter(Boolean), cooldown_seconds: Number(cooldown) || 3600 },
      },
    }),
    onSuccess: async () => {
      setNotice("Global settings saved.");
      setError("");
      await queryClient.invalidateQueries({ queryKey: queryKeys.deploymentSettings() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.currentUser() });
    },
    onError: (reason) => { setError(reason instanceof Error ? reason.message : "Could not save global settings."); setNotice(""); },
  });
  const testMutation = useMutation({
    mutationFn: sendNotificationTest,
    onSuccess: (result) => { setNotice(result.detail); setError(""); },
    onError: (reason) => { setError(reason instanceof Error ? reason.message : "Test email failed. Check SMTP and notification recipients."); setNotice(""); },
  });

  const runtime = runtimeQuery.data;
  const mail = runtime?.email;
  const localRelayDefault = Boolean(mail && ["localhost", "127.0.0.1"].includes(mail.host.toLowerCase()) && mail.port === 25);
  const mailStatus = !mail?.host_configured || !mail.from_email || !mail.backend.toLowerCase().includes("smtp")
    ? "Needs configuration"
    : localRelayDefault ? "Local relay default · verify delivery" : "Settings loaded · send a test";

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Administration</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Global settings</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">Site-wide defaults and mail delivery. These controls affect the whole MSConnect instance, not one project.</p>
      </header>
      <AdminTabs />
      {error ? <div role="alert" className="break-words rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</div> : null}
      {notice ? <div role="status" aria-live="polite" className="rounded-md border bg-secondary/40 px-4 py-3 text-sm">{notice}</div> : null}

      <Card>
        <CardHeader><CardTitle>Email delivery & account setup</CardTitle><CardDescription>Invitation and verification links use the web server’s mail configuration. SMTP secrets are never shown in MSConnect.</CardDescription></CardHeader>
        <CardContent className="grid gap-5 lg:grid-cols-[1fr_1fr]">
          {runtimeQuery.isLoading ? <p className="text-sm text-muted-foreground">Checking server configuration…</p> : runtimeQuery.isError ? <p role="alert" className="text-sm text-destructive">{runtimeQuery.error.message}</p> : (
            <div className="grid content-start gap-2 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-2"><span>Mail transport</span><strong>{mailStatus}</strong></div>
              <div className="flex flex-wrap justify-between gap-2"><span className="text-muted-foreground">Backend</span><span className="max-w-full break-all text-right">{mail?.backend || "Not set"}</span></div>
              <div className="flex flex-wrap justify-between gap-2"><span className="text-muted-foreground">SMTP host / port</span><span>{mail?.host || "Not set"} {mail?.host ? `· ${mail.port}` : ""}</span></div>
              <div className="flex flex-wrap justify-between gap-2"><span className="text-muted-foreground">From address</span><span className="break-all text-right">{mail?.from_email || "Not set"}</span></div>
              <div className="flex flex-wrap justify-between gap-2"><span className="text-muted-foreground">TLS / credentials</span><span>{mail?.use_tls ? "TLS on" : "TLS off"} · {mail?.credentials_configured ? "credentials present" : "no credentials detected"}</span></div>
              <div className="flex flex-wrap justify-between gap-2"><span className="text-muted-foreground">Public signup</span><span>{runtime?.public_signup_enabled ? "Enabled" : "Disabled; invite users from this admin area"}</span></div>
            </div>
          )}
          <div className="rounded-md border bg-secondary/20 p-4 text-sm">
            <h2 className="font-semibold">Set up email</h2>
            <ol className="mt-2 list-inside list-decimal space-y-1.5 text-muted-foreground">
              <li>Set <code>EMAIL_HOST</code>, <code>EMAIL_PORT</code>, <code>EMAIL_HOST_USER</code>, <code>EMAIL_HOST_PASSWORD</code>, <code>EMAIL_USE_TLS</code>, and <code>DEFAULT_FROM_EMAIL</code> in the server’s private environment file.</li>
              <li>Recreate the web service so it loads the updated environment.</li>
              <li>Add notification recipients below, save, then send a test email.</li>
            </ol>
            <p className="mt-3 text-xs text-muted-foreground">Keep mail credentials out of projects, user profiles, and source control. Public signup is deployment-controlled; admin invitations work while it is disabled.</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Instance defaults</CardTitle><CardDescription>Applied across project preflight and site-level processing configuration.</CardDescription></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field label="DIA-NN threads"><Input name="global_diann_threads" inputMode="numeric" value={threads} onChange={(event) => setThreads(event.target.value)} placeholder="1" /></Field>
          <Field label="DIA-NN temporary directory"><Input name="global_diann_temp" value={tempPath} onChange={(event) => setTempPath(event.target.value)} placeholder="/scratch/diann" /></Field>
          <Field label="Default PRTC Skyline pipeline"><PipelineSelect name="default_prtc_pipeline" value={prtcPipeline} onChange={setPrtcPipeline} pipelines={pipelines} /></Field>
          <Field label="Default targeted Skyline pipeline"><PipelineSelect name="default_targeted_pipeline" value={targetedPipeline} onChange={setTargetedPipeline} pipelines={pipelines} /></Field>
          <Field label="Notification recipients (comma-separated)"><Input name="global_notification_recipients" type="text" autoComplete="off" spellCheck={false} value={recipients} onChange={(event) => setRecipients(event.target.value)} placeholder="ops@example.org, pi@example.org" /></Field>
          <Field label="Notification cooldown (seconds)"><Input name="global_notification_cooldown" type="number" min="0" inputMode="numeric" value={cooldown} onChange={(event) => setCooldown(event.target.value)} /></Field>
          <div className="flex flex-wrap items-end gap-2 md:col-span-2">
            <Button variant="secondary" onClick={() => testMutation.mutate()} disabled={testMutation.isPending}>{testMutation.isPending ? "Sending test…" : "Send test email"}</Button>
            <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>{saveMutation.isPending ? "Saving…" : "Save global settings"}</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Instance identity</CardTitle><CardDescription>Set the primary lab or workspace name displayed beside MSConnect in the application header. The deployment profile remains deployment-managed.</CardDescription></CardHeader>
        <CardContent className="grid gap-4 text-sm sm:grid-cols-2">
          <Field label="Primary lab / workspace name">
            <Input name="primary_lab_name" value={primaryLabName} onChange={(event) => setPrimaryLabName(event.target.value)} placeholder="e.g. Kelly Lab" maxLength={80} />
          </Field>
          <div><span className="text-muted-foreground">Instance profile</span><div className="mt-1 font-medium">{runtime?.instance_profile ?? (runtimeQuery.isLoading ? "Loading…" : "Unavailable")}</div></div>
          <div><span className="text-muted-foreground">Default facility</span><div className="mt-1 font-medium">{runtime?.default_facility_slug || "Not set"}</div></div>
          <div className="flex items-end sm:col-span-2">
            <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending || deploymentQuery.isLoading}>
              {saveMutation.isPending ? "Saving…" : "Save global settings"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function PipelineSelect({ name, value, onChange, pipelines }: { name: string; value: string; onChange: (value: string) => void; pipelines: Array<{ id: number; name: string; version: string }> }) {
  return <select name={name} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={value} onChange={(event) => onChange(event.target.value)}><option value="">Unset</option>{pipelines.map((pipeline) => <option key={pipeline.id} value={pipeline.id}>{pipeline.name} · {pipeline.version}</option>)}</select>;
}

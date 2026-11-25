import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Copy, KeyRound, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AdminTabs } from "@/features/admin/admin-tabs";
import { createProvisionedAgent, deleteProvisionedAgent, fetchAgentProvisioning, fetchInstruments, queryKeys } from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import type { AgentProvisioningCreated, ProvisionedAgent } from "@/lib/api/queries";
import ProcessingAdminPage from "@/features/processing/processing-admin-page";

export default function AgentProvisioningPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const view = searchParams.get("view") === "compute" ? "compute" : "setup";
  const [createOpen, setCreateOpen] = useState(false);
  const [role, setRole] = useState<"watcher" | "processor">("watcher");
  const [name, setName] = useState("");
  const [engine, setEngine] = useState("diann");
  const [instrumentId, setInstrumentId] = useState("");
  const [sourceRoot, setSourceRoot] = useState("C:\\MSData\\VendorOutput");
  const [rawRoot, setRawRoot] = useState("/mnt/msconnect/raw");
  const [resultsRoot, setResultsRoot] = useState("/mnt/msconnect/results");
  const [sharedRoot, setSharedRoot] = useState("/mnt/msconnect/shared");
  const [created, setCreated] = useState<AgentProvisioningCreated | null>(null);
  const [copied, setCopied] = useState<"key" | "setup" | null>(null);
  const [copyError, setCopyError] = useState("");
  const agentsQuery = useQuery({ queryKey: ["agent-provisioning"], queryFn: fetchAgentProvisioning });
  const instrumentsQuery = useQuery({ queryKey: ["instruments", { page: 1, page_size: 500 }], queryFn: () => fetchInstruments({ page: 1, page_size: 500 }) });
  const instruments = (instrumentsQuery.data?.results ?? []).filter((item) => item.active && ["ms", "lcms"].includes(item.instrument_type));
  const createMutation = useMutation({
    mutationFn: () => createProvisionedAgent(role === "watcher"
      ? { role, name: name.trim(), ms_instrument: Number(instrumentId), source_root: sourceRoot.trim(), spool_root: "C:\\MSConnect2\\spool" }
      : { role, name: name.trim(), engine, raw_root: rawRoot.trim(), results_root: resultsRoot.trim(), shared_root: sharedRoot.trim() }),
    onSuccess: (value) => { setCreated(value); void agentsQuery.refetch(); },
  });
  const deleteMutation = useMutation({
    mutationFn: ({ role: targetRole, id }: { role: "watcher" | "processor"; id: number }) => deleteProvisionedAgent(targetRole, id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agent-provisioning"] }),
        queryClient.invalidateQueries({ queryKey: queryKeys.processingNodes() }),
      ]);
    },
  });
  const resetForm = () => { setCreated(null); setCopied(null); setCopyError(""); setName(""); setCreateOpen(false); };
  const copyValue = async (value: string, target: "key" | "setup") => {
    setCopyError("");
    const didCopy = await copyText(value);
    if (!didCopy) {
      setCopied(null);
      setCopyError("Your browser blocked clipboard access. Select the key or setup text and press Ctrl+C (or Command+C on Mac).");
      return;
    }
    setCopied(target);
    window.setTimeout(() => setCopied((current) => current === target ? null : current), 1600);
  };

  return <div className="grid min-w-0 gap-4">
    <Breadcrumbs items={[{ label: "Administration", href: "/admin" }, { label: "Nodes & compute" }, ...(view === "compute" ? [{ label: "Compute" }] : [])]} />
    <PageHero eyebrow="Machine access" title="Nodes & compute" description="Set up watcher and processor computers, monitor their health, and manage processing capacity." actions={<><Button variant="secondary" onClick={() => void agentsQuery.refetch()}><RefreshCw className="h-4 w-4" />Refresh</Button><Button onClick={() => { setSearchParams({ view: "setup" }); setCreateOpen(true); }}><Plus className="h-4 w-4" />Add a new node</Button></>} />
    <AdminTabs />

    <nav aria-label="Nodes and compute sections" className="flex w-fit gap-1 border-b">
      <button type="button" aria-current={view === "setup" ? "page" : undefined} onClick={() => setSearchParams({ view: "setup" })} className={`px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${view === "setup" ? "border-b-2 border-primary font-semibold" : "text-muted-foreground hover:text-foreground"}`}>Node setup</button>
      <button type="button" aria-current={view === "compute" ? "page" : undefined} onClick={() => setSearchParams({ view: "compute", type: searchParams.get("type") || "processor" })} className={`px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${view === "compute" ? "border-b-2 border-primary font-semibold" : "text-muted-foreground hover:text-foreground"}`}>Compute controls</button>
    </nav>

    {view === "compute" ? <ProcessingAdminPage embedded /> : <>
    {created ? <ProvisioningSteps created={created} copied={copied} copyError={copyError} onCopy={copyValue} onClose={resetForm} /> : createOpen ? <Card>
      <CardHeader><CardTitle>Add a computer</CardTitle><CardDescription>Choose Watcher for instrument data intake or Processor for analysis work.</CardDescription></CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="grid gap-1 text-sm font-medium">Computer type<select className="h-10 rounded-md border border-input bg-background px-3" value={role} onChange={(event) => setRole(event.target.value as "watcher" | "processor")}><option value="watcher">Watcher · instrument data intake</option><option value="processor">Processor · analysis compute</option></select></label>
          <label className="grid gap-1 text-sm font-medium">Computer name<Input value={name} onChange={(event) => setName(event.target.value)} placeholder={role === "watcher" ? "ms-acquisition-01" : "diann-wsl-01"} autoComplete="off" /></label>
          {role === "watcher" ? <>
            <label className="grid gap-1 text-sm font-medium">Assigned MS instrument<select className="h-10 rounded-md border border-input bg-background px-3" value={instrumentId} onChange={(event) => setInstrumentId(event.target.value)}><option value="">Select an instrument</option>{instruments.map((item) => <option key={item.id} value={item.id}>{item.nickname} · {item.manufacturer} {item.model}</option>)}</select></label>
            <label className="grid gap-1 text-sm font-medium">Acquisition folder on that computer<Input value={sourceRoot} onChange={(event) => setSourceRoot(event.target.value)} placeholder="C:\\MSData\\VendorOutput" /></label>
          </> : <>
            <p className="text-sm text-muted-foreground md:col-span-2">The setup block runs in Ubuntu on WSL2. Install WSL2 and Docker Desktop with Ubuntu integration first, and mount the server’s raw, results, and shared-reference folders in WSL. The block creates the expected directories, then checks that they are backed by mounted shares.</p>
            <label className="grid gap-1 text-sm font-medium">Processor engine<select className="h-10 rounded-md border border-input bg-background px-3" value={engine} onChange={(event) => setEngine(event.target.value)}><option value="diann">DIA-NN 2.7.0 through Nextflow</option></select></label>
            <div className="hidden md:block" />
            <label className="grid gap-1 text-sm font-medium">Raw file share mounted in WSL<Input value={rawRoot} onChange={(event) => setRawRoot(event.target.value)} /></label>
            <label className="grid gap-1 text-sm font-medium">Results share mounted in WSL<Input value={resultsRoot} onChange={(event) => setResultsRoot(event.target.value)} /></label>
            <label className="grid gap-1 text-sm font-medium md:col-span-2">References and workflow share mounted in WSL<Input value={sharedRoot} onChange={(event) => setSharedRoot(event.target.value)} /></label>
          </>}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!name.trim() || (role === "watcher" && (!instrumentId || !sourceRoot.trim())) || createMutation.isPending} onClick={() => createMutation.mutate()}><KeyRound className="h-4 w-4" />{createMutation.isPending ? "Creating…" : "Create node and key"}</Button>
          <Button type="button" variant="ghost" onClick={() => setCreateOpen(false)}>Cancel</Button>
          <span className="text-xs text-muted-foreground">The new key is shown once. Copy it into the target computer’s local environment.</span>
        </div>
        {createMutation.error instanceof Error ? <p role="alert" className="text-sm text-destructive">{createMutation.error.message}</p> : null}
      </CardContent>
    </Card> : null}

    {!created && !createOpen ? <Card>
      <CardHeader><CardTitle>Registered computers</CardTitle><CardDescription>Provisioning status and latest check-in for each Watcher and Processor.</CardDescription></CardHeader>
      <CardContent className="grid gap-5">
        {agentsQuery.isError ? <p role="alert" className="text-sm text-destructive">Could not load registered computers: {agentsQuery.error.message}</p> : null}
        {deleteMutation.error instanceof Error ? <p role="alert" className="text-sm text-destructive">Could not delete node: {deleteMutation.error.message}</p> : null}
        <AgentList title="Watchers" icon="watcher" agents={agentsQuery.data?.watchers ?? []} busy={deleteMutation.isPending} onDelete={(agent) => { if (window.confirm(`Delete ${agent.name}? Its registered routes will also be removed.`)) deleteMutation.mutate({ role: "watcher", id: agent.id }); }} />
        <AgentList title="Processors" icon="processor" agents={agentsQuery.data?.processors ?? []} busy={deleteMutation.isPending} onDelete={(agent) => { if (window.confirm(`Delete ${agent.name}? Its node record and event history will be removed.`)) deleteMutation.mutate({ role: "processor", id: agent.id }); }} />
      </CardContent>
    </Card> : null}
    </>}
  </div>;
}

function ProvisioningSteps({ created, copied, copyError, onCopy, onClose }: { created: AgentProvisioningCreated; copied: "key" | "setup" | null; copyError: string; onCopy: (value: string, target: "key" | "setup") => void; onClose: () => void }) {
  const isProcessor = created.role === "processor";
  const commandTitle = isProcessor ? "Bash setup block · Ubuntu on WSL2" : "PowerShell setup block · MS acquisition computer";
  return <Card>
    <CardHeader><CardTitle>Set up {created.name}</CardTitle><CardDescription>{isProcessor
      ? "On the Processor computer, open Ubuntu (WSL2). Copy the Bash block below and paste it into the terminal. When it asks for the key, copy the key from this page, paste it into the terminal, and press Enter. The script checks the connection and starts the Processor."
      : "On the mass spectrometer acquisition computer, open PowerShell. Copy the PowerShell block below and paste it into the window. When it asks for the key, copy the key from this page, paste it into PowerShell, and press Enter. The script checks the connection and starts the Watcher."}</CardDescription></CardHeader>
    <CardContent className="grid gap-4">
      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
        <div className="min-w-0"><div className="text-xs font-bold uppercase text-muted-foreground">One-time node key</div><code className="mt-1 block break-all rounded-md bg-muted p-3 text-sm">{created.token}</code></div>
        <Button variant="secondary" onClick={() => onCopy(created.token, "key")}>{copied === "key" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}{copied === "key" ? "Copied" : "Copy key"}</Button>
      </div>
      <p className="text-sm text-warning">The key is shown once and is stored only as a hash. Keep this page open until you have pasted it into the setup prompt.</p>
      <InstructionBlock title={commandTitle} value={created.instructions.install_and_check} copied={copied === "setup"} onCopy={() => onCopy(created.instructions.install_and_check, "setup")} />
      {copyError ? <p role="alert" aria-live="assertive" className="text-sm text-destructive">{copyError}</p> : null}
      <div className="rounded-md border bg-secondary/20 p-3 text-sm text-muted-foreground">The key is active now. The setup block runs a connection check automatically; keep the Watcher PowerShell window open, or wait for the Processor setup to report that its service started.</div>
      <Button variant="secondary" className="w-fit" onClick={onClose}>Return to Nodes & compute</Button>
    </CardContent>
  </Card>;
}

function InstructionBlock({ title, value, copied, onCopy }: { title: string; value: string; copied: boolean; onCopy: () => void }) {
  return <section className="grid min-w-0 gap-2"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">{title}</h3><Button size="sm" variant="secondary" onClick={onCopy}>{copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}{copied ? "Copied" : "Copy setup block"}</Button></div><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-md bg-slate-950 p-4 text-xs leading-5 text-slate-100"><code>{value}</code></pre></section>;
}

function AgentList({ title, agents, icon, busy, onDelete }: { title: string; agents: ProvisionedAgent[]; icon: "watcher" | "processor"; busy: boolean; onDelete: (agent: ProvisionedAgent) => void }) {
  return <section className="grid gap-2"><h3 className="text-sm font-semibold">{title}</h3>{agents.length ? agents.map((agent) => <div key={`${icon}-${agent.id}`} className="grid min-w-0 gap-2 border-t py-2 sm:grid-cols-[minmax(0,1fr)_130px_180px_auto] sm:items-center"><div className="min-w-0"><div className="break-words font-medium">{agent.name}</div><div className="text-xs text-muted-foreground">{agent.node_type || (agent.active ? "Watcher active" : "Watcher inactive")}</div></div><span className={agent.provisioning_status === "ready" ? "text-sm font-medium text-success" : "text-sm font-medium text-warning"}>{agent.provisioning_status === "ready" ? "Ready" : "Setup pending"}</span><span className="text-xs text-muted-foreground">Last seen {formatAgentDate(agent.last_seen_at || agent.last_heartbeat_at)}</span><Button type="button" variant="destructive" size="sm" disabled={busy} onClick={() => onDelete(agent)}><Trash2 className="h-3.5 w-3.5" />Delete</Button></div>) : <div className="border border-dashed p-3 text-sm text-muted-foreground">No {title.toLowerCase()} registered.</div>}</section>;
}

function formatAgentDate(value?: string | null) {
  if (!value) return "never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "never" : date.toLocaleString();
}

async function copyText(value: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Clipboard API is unavailable on plain HTTP origins in many browsers.
  }

  let fallback: HTMLTextAreaElement | null = null;
  try {
    fallback = document.createElement("textarea");
    fallback.value = value;
    fallback.setAttribute("readonly", "");
    fallback.style.position = "fixed";
    fallback.style.top = "0";
    fallback.style.left = "-9999px";
    document.body.appendChild(fallback);
    fallback.focus();
    fallback.select();
    fallback.setSelectionRange(0, value.length);
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    fallback?.remove();
  }
}

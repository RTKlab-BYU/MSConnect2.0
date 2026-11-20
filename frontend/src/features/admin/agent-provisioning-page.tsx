import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Copy, KeyRound, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AdminTabs } from "@/features/admin/admin-tabs";
import { activateProvisionedAgent, createProvisionedAgent, fetchAgentProvisioning, fetchInstruments, queryKeys } from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";
import type { AgentProvisioningCreated, ProvisionedAgent } from "@/lib/api/queries";

export default function AgentProvisioningPage() {
  const [role, setRole] = useState<"watcher" | "processor">("watcher");
  const [name, setName] = useState("");
  const [engine, setEngine] = useState("diann");
  const [instrumentId, setInstrumentId] = useState("");
  const [sourceRoot, setSourceRoot] = useState("C:\\MSData\\VendorOutput");
  const [rawRoot, setRawRoot] = useState("/mnt/msconnect/raw");
  const [resultsRoot, setResultsRoot] = useState("/mnt/msconnect/results");
  const [sharedRoot, setSharedRoot] = useState("/mnt/msconnect/shared");
  const [created, setCreated] = useState<AgentProvisioningCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const agentsQuery = useQuery({ queryKey: ["agent-provisioning"], queryFn: fetchAgentProvisioning });
  const instrumentsQuery = useQuery({ queryKey: ["instruments", { page: 1, page_size: 500 }], queryFn: () => fetchInstruments({ page: 1, page_size: 500 }) });
  const instruments = (instrumentsQuery.data?.results ?? []).filter((item) => item.active && ["ms", "lcms"].includes(item.instrument_type));
  const createMutation = useMutation({
    mutationFn: () => createProvisionedAgent(role === "watcher"
      ? { role, name: name.trim(), ms_instrument: Number(instrumentId), source_root: sourceRoot.trim(), spool_root: "C:\\MSConnect2\\spool" }
      : { role, name: name.trim(), engine, raw_root: rawRoot.trim(), results_root: resultsRoot.trim(), shared_root: sharedRoot.trim() }),
    onSuccess: (value) => { setCreated(value); void agentsQuery.refetch(); },
  });
  const readyMutation = useMutation({
    mutationFn: ({ agentRole, id }: { agentRole: "watcher" | "processor"; id: number }) => activateProvisionedAgent(agentRole, id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["agent-provisioning"] });
      await queryClient.invalidateQueries({ queryKey: queryKeys.processingNodes() });
      await queryClient.invalidateQueries({ queryKey: ["acquisition-agents"] });
      setCreated((current) => current ? { ...current, provisioning_status: "ready" } : current);
    },
  });
  const resetForm = () => { setCreated(null); setCopied(false); setName(""); };
  const copyText = async (value: string) => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return <div className="grid min-w-0 gap-4">
    <Breadcrumbs items={[{ label: "Administration", href: "/admin" }, { label: "Agent setup" }]} />
    <PageHero eyebrow="Machine access" title="Agent setup" description="Create a machine identity, install its runner, then activate its individual key. Keys are stored hashed and shown only once." actions={<Button variant="secondary" onClick={() => void agentsQuery.refetch()}><RefreshCw className="h-4 w-4" />Refresh</Button>} />
    <AdminTabs />

    {created ? <ProvisioningSteps created={created} copied={copied} onCopy={copyText} onReady={() => readyMutation.mutate({ agentRole: created.role, id: created.id })} onClose={resetForm} pending={readyMutation.isPending} error={readyMutation.error instanceof Error ? readyMutation.error.message : ""} /> : <Card>
      <CardHeader><CardTitle>Register a computer</CardTitle><CardDescription>Each watcher or processor receives its own credential and setup instructions.</CardDescription></CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="grid gap-1 text-sm font-medium">Computer role<select className="h-10 rounded-md border border-input bg-background px-3" value={role} onChange={(event) => setRole(event.target.value as "watcher" | "processor")}><option value="watcher">MS acquisition watcher</option><option value="processor">DIA-NN processor (WSL2)</option></select></label>
          <label className="grid gap-1 text-sm font-medium">Computer name<Input value={name} onChange={(event) => setName(event.target.value)} placeholder={role === "watcher" ? "ms-acquisition-01" : "diann-wsl-01"} autoComplete="off" /></label>
          {role === "watcher" ? <>
            <label className="grid gap-1 text-sm font-medium">Assigned MS instrument<select className="h-10 rounded-md border border-input bg-background px-3" value={instrumentId} onChange={(event) => setInstrumentId(event.target.value)}><option value="">Select an instrument</option>{instruments.map((item) => <option key={item.id} value={item.id}>{item.nickname} · {item.manufacturer} {item.model}</option>)}</select></label>
            <label className="grid gap-1 text-sm font-medium">Acquisition folder on that computer<Input value={sourceRoot} onChange={(event) => setSourceRoot(event.target.value)} placeholder="C:\\MSData\\VendorOutput" /></label>
          </> : <>
            <label className="grid gap-1 text-sm font-medium">Processor engine<select className="h-10 rounded-md border border-input bg-background px-3" value={engine} onChange={(event) => setEngine(event.target.value)}><option value="diann">DIA-NN 2.7.0 through Nextflow</option></select></label>
            <div className="hidden md:block" />
            <label className="grid gap-1 text-sm font-medium">Raw file share mounted in WSL<Input value={rawRoot} onChange={(event) => setRawRoot(event.target.value)} /></label>
            <label className="grid gap-1 text-sm font-medium">Results share mounted in WSL<Input value={resultsRoot} onChange={(event) => setResultsRoot(event.target.value)} /></label>
            <label className="grid gap-1 text-sm font-medium md:col-span-2">References and workflow share mounted in WSL<Input value={sharedRoot} onChange={(event) => setSharedRoot(event.target.value)} /></label>
          </>}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!name.trim() || (role === "watcher" && (!instrumentId || !sourceRoot.trim())) || createMutation.isPending} onClick={() => createMutation.mutate()}><KeyRound className="h-4 w-4" />{createMutation.isPending ? "Creating…" : "Create agent and key"}</Button>
          <span className="text-xs text-muted-foreground">The new key is shown once. Copy it into the target computer’s local environment.</span>
        </div>
        {createMutation.error instanceof Error ? <p role="alert" className="text-sm text-destructive">{createMutation.error.message}</p> : null}
      </CardContent>
    </Card>}

    {!created ? <Card>
      <CardHeader><CardTitle>Registered computers</CardTitle><CardDescription>Activation status and last check-in. The server accepts an agent key as soon as you mark it ready; no server restart is needed.</CardDescription></CardHeader>
      <CardContent className="grid gap-5">
        {agentsQuery.isError ? <p role="alert" className="text-sm text-destructive">Could not load agents: {agentsQuery.error.message}</p> : null}
        <AgentList title="Acquisition watchers" icon="watcher" agents={agentsQuery.data?.watchers ?? []} />
        <AgentList title="Processors" icon="processor" agents={agentsQuery.data?.processors ?? []} />
      </CardContent>
    </Card> : null}
  </div>;
}

function ProvisioningSteps({ created, copied, onCopy, onReady, onClose, pending, error }: { created: AgentProvisioningCreated; copied: boolean; onCopy: (value: string) => void; onReady: () => void; onClose: () => void; pending: boolean; error: string }) {
  const active = created.provisioning_status === "ready";
  return <Card>
    <CardHeader><CardTitle>Set up {created.name}</CardTitle><CardDescription>Run the install and local checks first. After they pass, activate this machine identity, then run the connection check and keep the agent running.</CardDescription></CardHeader>
    <CardContent className="grid gap-4">
      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-start">
        <div className="min-w-0"><div className="text-xs font-bold uppercase text-muted-foreground">One-time agent key</div><code className="mt-1 block break-all rounded-md bg-muted p-3 text-sm">{created.token}</code></div>
        <Button variant="secondary" onClick={() => onCopy(created.token)}>{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}{copied ? "Copied" : "Copy key"}</Button>
      </div>
      <p className="text-sm text-warning">Save this key now. MSConnect stores only its hash; if it is lost, revoke this agent and create a replacement.</p>
      <InstructionBlock title="1. Install and run local checks" value={created.instructions.install_and_check} onCopy={onCopy} />
      <div className="flex flex-wrap items-center gap-3 border-y py-3">
        <Button disabled={active || pending} onClick={onReady}><ShieldCheck className="h-4 w-4" />{active ? "Agent key activated" : pending ? "Activating…" : "Ready to connect"}</Button>
        <span className="text-sm text-muted-foreground">After activation, the agent can authenticate and appear in the live node list.</span>
      </div>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {active ? <InstructionBlock title="2. Check the live API and start the agent" value={created.instructions.after_ready} onCopy={onCopy} /> : null}
      {active ? <Button variant="secondary" className="w-fit" onClick={onClose}>Finish setup</Button> : null}
    </CardContent>
  </Card>;
}

function InstructionBlock({ title, value, onCopy }: { title: string; value: string; onCopy: (value: string) => void }) {
  return <section className="grid min-w-0 gap-2"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">{title}</h3><Button size="sm" variant="ghost" onClick={() => onCopy(value)}><Copy className="h-3.5 w-3.5" />Copy commands</Button></div><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-md bg-slate-950 p-4 text-xs leading-5 text-slate-100"><code>{value}</code></pre></section>;
}

function AgentList({ title, agents, icon }: { title: string; agents: ProvisionedAgent[]; icon: "watcher" | "processor" }) {
  return <section className="grid gap-2"><h3 className="text-sm font-semibold">{title}</h3>{agents.length ? agents.map((agent) => <div key={`${icon}-${agent.id}`} className="grid min-w-0 gap-2 border-t py-2 sm:grid-cols-[minmax(0,1fr)_130px_180px] sm:items-center"><div className="min-w-0"><div className="break-words font-medium">{agent.name}</div><div className="text-xs text-muted-foreground">{agent.node_type || (agent.active ? "Watcher active" : "Watcher inactive")}</div></div><span className={agent.provisioning_status === "ready" ? "text-sm font-medium text-success" : "text-sm font-medium text-warning"}>{agent.provisioning_status === "ready" ? "Ready" : "Setup pending"}</span><span className="text-xs text-muted-foreground">Last seen {formatAgentDate(agent.last_seen_at || agent.last_heartbeat_at)}</span></div>) : <div className="border border-dashed p-3 text-sm text-muted-foreground">No {title.toLowerCase()} registered.</div>}</section>;
}

function formatAgentDate(value?: string | null) {
  if (!value) return "never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "never" : date.toLocaleString();
}

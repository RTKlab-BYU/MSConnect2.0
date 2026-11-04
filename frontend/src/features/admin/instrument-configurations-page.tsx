import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import {
  createInstrument,
  createInstrumentConfiguration,
  fetchAcquisitionAgents,
  fetchCurrentUser,
  fetchFacilities,
  fetchInstrumentConfigurations,
  fetchInstruments,
  queryKeys,
  type InstrumentConfigurationPayload,
  updateInstrumentConfiguration,
  updateAcquisitionAgent,
} from "@/lib/api/queries";
import type { InstrumentConfiguration } from "@/lib/api/types";

const none = "none";

type ConfigurationDraft = {
  facility: string;
  name: string;
  lc_instrument: string;
  ms_instrument: string;
  method_name: string;
  column_description: string;
  gradient_description: string;
  ion_source: string;
  active: boolean;
};

const emptyDraft: ConfigurationDraft = {
  facility: "",
  name: "",
  lc_instrument: none,
  ms_instrument: none,
  method_name: "",
  column_description: "",
  gradient_description: "",
  ion_source: "",
  active: true,
};

export default function InstrumentConfigurationsPage() {
  const queryClient = useQueryClient();
  const currentUserQuery = useQuery({ queryKey: queryKeys.currentUser(), queryFn: fetchCurrentUser });
  const facilitiesQuery = useQuery({
    queryKey: queryKeys.facilities({ page: 1, page_size: 200 }),
    queryFn: () => fetchFacilities({ page: 1, page_size: 200 }),
  });
  const instrumentsQuery = useQuery({
    queryKey: queryKeys.instruments({ page: 1, page_size: 200 }),
    queryFn: () => fetchInstruments({ page: 1, page_size: 200 }),
  });
  const configurationsQuery = useQuery({
    queryKey: queryKeys.instrumentConfigurations({ page: 1, page_size: 200 }),
    queryFn: () => fetchInstrumentConfigurations({ page: 1, page_size: 200 }),
  });
  const acquisitionAgentsQuery = useQuery({
    queryKey: queryKeys.acquisitionAgents({ page: 1, page_size: 200 }),
    queryFn: () => fetchAcquisitionAgents({ page: 1, page_size: 200 }),
  });
  const facilities = (facilitiesQuery.data?.results ?? []).filter((facility) => facility.active);
  const instruments = (instrumentsQuery.data?.results ?? []).filter((instrument) => instrument.active);
  const configurations = configurationsQuery.data?.results ?? [];
  const isAdmin = currentUserQuery.data?.global_role === "admin" || currentUserQuery.data?.is_superuser;
  const [draft, setDraft] = useState<ConfigurationDraft>(emptyDraft);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [instrumentDraft, setInstrumentDraft] = useState({ nickname: "", facility: "", instrument_type: "lc" as "lc" | "ms" | "lcms", manufacturer: "", model: "", serial_number: "" });

  useEffect(() => {
    if (!draft.facility && facilities.length) setDraft((current) => ({ ...current, facility: String(facilities[0].id) }));
    if (!instrumentDraft.facility && facilities.length) setInstrumentDraft((current) => ({ ...current, facility: String(facilities[0].id) }));
  }, [draft.facility, facilities, instrumentDraft.facility]);

  const availableInstruments = useMemo(
    () => instruments.filter((instrument) => String(instrument.facility) === draft.facility),
    [draft.facility, instruments],
  );
  const instrumentById = useMemo(() => new Map(instruments.map((instrument) => [String(instrument.id), instrument])), [instruments]);

  const saveMutation = useMutation({
    mutationFn: (payload: InstrumentConfigurationPayload) => editingId
      ? updateInstrumentConfiguration(editingId, payload)
      : createInstrumentConfiguration(payload),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ["instrument-configurations"] });
      setEditingId(null);
      setDraft({ ...emptyDraft, facility: String(saved.facility) });
      setError("");
      setMessage(`${saved.name} saved.`);
    },
    onError: (reason) => { setMessage(""); setError(reason instanceof Error ? reason.message : "Could not save the LC-MS configuration."); },
  });
  const instrumentMutation = useMutation({
    mutationFn: createInstrument,
    onSuccess: async (instrument) => {
      await queryClient.invalidateQueries({ queryKey: ["instruments"] });
      setInstrumentDraft((current) => ({ ...current, nickname: "", manufacturer: "", model: "", serial_number: "" }));
      setDraft((current) => ({ ...current, facility: String(instrument.facility) }));
      setMessage(`${instrument.nickname} registered.`);
      setError("");
    },
    onError: (reason) => { setMessage(""); setError(reason instanceof Error ? reason.message : "Could not register the instrument."); },
  });

  function editConfiguration(configuration: InstrumentConfiguration) {
    setEditingId(Number(configuration.id));
    setDraft({
      facility: String(configuration.facility),
      name: configuration.name,
      lc_instrument: configuration.lc_instrument ? String(configuration.lc_instrument) : none,
      ms_instrument: configuration.ms_instrument ? String(configuration.ms_instrument) : none,
      method_name: configuration.method_name,
      column_description: configuration.column_description,
      gradient_description: configuration.gradient_description,
      ion_source: configuration.ion_source,
      active: configuration.active,
    });
    setMessage("");
    setError("");
  }

  function submitConfiguration(event: FormEvent) {
    event.preventDefault();
    const payload: InstrumentConfigurationPayload = {
      facility: Number(draft.facility),
      name: draft.name.trim(),
      lc_instrument: draft.lc_instrument === none ? null : Number(draft.lc_instrument),
      ms_instrument: draft.ms_instrument === none ? null : Number(draft.ms_instrument),
      method_name: draft.method_name.trim(),
      column_description: draft.column_description.trim(),
      gradient_description: draft.gradient_description.trim(),
      ion_source: draft.ion_source.trim(),
      active: draft.active,
      metadata: {},
    };
    saveMutation.mutate(payload);
  }

  function submitInstrument(event: FormEvent) {
    event.preventDefault();
    instrumentMutation.mutate({
      nickname: instrumentDraft.nickname.trim(),
      facility: Number(instrumentDraft.facility),
      instrument_type: instrumentDraft.instrument_type,
      manufacturer: instrumentDraft.manufacturer.trim(),
      model: instrumentDraft.model.trim(),
      serial_number: instrumentDraft.serial_number.trim(),
      active: true,
      metadata: {},
    });
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-4">
      <Breadcrumbs items={[{ label: "Projects", href: "/projects" }, { label: "LC-MS setups" }]} />
      <PageHero
        eyebrow="Facility operations"
        title="LC-MS setups"
        description="Register the facility’s instruments and maintain the LC method and MS pairing used by acquisition worklists. Each watcher stays attached to its configured MS; LC method changes are captured on each managed setup."
        actions={<Button asChild variant="secondary"><Link to="/projects">Back to projects</Link></Button>}
      />
      {error ? <div role="alert" className="break-words rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</div> : null}
      {message ? <div role="status" className="rounded-md border bg-secondary/40 px-4 py-3 text-sm">{message}</div> : null}

      {isAdmin ? (
        <Card>
          <CardHeader><CardTitle>Register a facility instrument</CardTitle><CardDescription>Administrators maintain the instrument inventory. Facility managers can select registered instruments when they build LC-MS setups.</CardDescription></CardHeader>
          <CardContent>
            {facilities.length ? (
              <form className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" onSubmit={submitInstrument}>
                <label className="grid gap-1.5 text-sm font-medium">Facility<select className="h-10 rounded-md border border-input bg-background px-3" required value={instrumentDraft.facility || String(facilities[0].id)} onChange={(event) => setInstrumentDraft((current) => ({ ...current, facility: event.target.value }))}>{facilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}</select></label>
                <label className="grid gap-1.5 text-sm font-medium">Instrument name<Input required value={instrumentDraft.nickname} onChange={(event) => setInstrumentDraft((current) => ({ ...current, nickname: event.target.value }))} /></label>
                <label className="grid gap-1.5 text-sm font-medium">Type<select className="h-10 rounded-md border border-input bg-background px-3" value={instrumentDraft.instrument_type} onChange={(event) => setInstrumentDraft((current) => ({ ...current, instrument_type: event.target.value as typeof current.instrument_type }))}><option value="lc">LC</option><option value="ms">MS</option><option value="lcms">LC-MS</option></select></label>
                <label className="grid gap-1.5 text-sm font-medium">Manufacturer<Input value={instrumentDraft.manufacturer} onChange={(event) => setInstrumentDraft((current) => ({ ...current, manufacturer: event.target.value }))} /></label>
                <label className="grid gap-1.5 text-sm font-medium">Model<Input value={instrumentDraft.model} onChange={(event) => setInstrumentDraft((current) => ({ ...current, model: event.target.value }))} /></label>
                <label className="grid gap-1.5 text-sm font-medium">Serial number<Input value={instrumentDraft.serial_number} onChange={(event) => setInstrumentDraft((current) => ({ ...current, serial_number: event.target.value }))} /></label>
                <div className="flex items-end"><Button type="submit" disabled={instrumentMutation.isPending}>{instrumentMutation.isPending ? "Registering…" : "Register instrument"}</Button></div>
              </form>
            ) : <p className="text-sm text-muted-foreground">No active facility is available in your access scope.</p>}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader><CardTitle>Watcher MS assignment</CardTitle><CardDescription>Each watcher computer is pinned to one MS. Administrators update the assignment; acquisition worklists must use a setup with the same MS.</CardDescription></CardHeader>
        <CardContent className="grid gap-3">
          {acquisitionAgentsQuery.data?.results.length ? acquisitionAgentsQuery.data.results.map((agent) => (
            <WatcherMsAssignment key={agent.id} agent={agent} instruments={instruments} canEdit={Boolean(isAdmin)} onSaved={() => queryClient.invalidateQueries({ queryKey: ["acquisition-agents"] })} />
          )) : <p className="text-sm text-muted-foreground">{acquisitionAgentsQuery.isLoading ? "Loading watchers…" : "No watchers are registered yet."}</p>}
          {acquisitionAgentsQuery.isError ? <p role="alert" className="text-sm text-destructive">{acquisitionAgentsQuery.error.message}</p> : null}
        </CardContent>
      </Card>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Card>
          <CardHeader><CardTitle>{editingId ? "Edit LC-MS setup" : "Add an LC-MS setup"}</CardTitle><CardDescription>Link the correct LC, method, and fixed MS to keep the acquisition configuration explicit.</CardDescription></CardHeader>
          <CardContent>
            {facilities.length ? (
              <form className="grid gap-3" onSubmit={submitConfiguration}>
                <label className="grid gap-1.5 text-sm font-medium">Facility<select className="h-10 rounded-md border border-input bg-background px-3" required value={draft.facility || String(facilities[0].id)} onChange={(event) => setDraft((current) => ({ ...current, facility: event.target.value, lc_instrument: none, ms_instrument: none }))}>{facilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}</select></label>
                <label className="grid gap-1.5 text-sm font-medium">Setup name<Input required value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} placeholder="e.g. Vanquish Neo · Exploris 480" /></label>
                <label className="grid gap-1.5 text-sm font-medium">LC instrument<select className="h-10 rounded-md border border-input bg-background px-3" required value={draft.lc_instrument} onChange={(event) => setDraft((current) => ({ ...current, lc_instrument: event.target.value }))}><option value={none}>Select LC instrument</option>{availableInstruments.filter((instrument) => instrument.instrument_type === "lc" || instrument.instrument_type === "lcms").map((instrument) => <option key={instrument.id} value={instrument.id}>{instrument.nickname}</option>)}</select></label>
                <label className="grid gap-1.5 text-sm font-medium">MS instrument<select className="h-10 rounded-md border border-input bg-background px-3" required value={draft.ms_instrument} onChange={(event) => setDraft((current) => ({ ...current, ms_instrument: event.target.value }))}><option value={none}>Select fixed MS instrument</option>{availableInstruments.filter((instrument) => instrument.instrument_type === "ms" || instrument.instrument_type === "lcms").map((instrument) => <option key={instrument.id} value={instrument.id}>{instrument.nickname}</option>)}</select></label>
                <label className="grid gap-1.5 text-sm font-medium">LC method name<Input required value={draft.method_name} onChange={(event) => setDraft((current) => ({ ...current, method_name: event.target.value }))} placeholder="e.g. 60 min DIA" /></label>
                <label className="grid gap-1.5 text-sm font-medium">Column<Input value={draft.column_description} onChange={(event) => setDraft((current) => ({ ...current, column_description: event.target.value }))} /></label>
                <label className="grid gap-1.5 text-sm font-medium">Gradient<textarea className="min-h-20 rounded-md border border-input bg-background px-3 py-2 text-sm" value={draft.gradient_description} onChange={(event) => setDraft((current) => ({ ...current, gradient_description: event.target.value }))} /></label>
                <label className="grid gap-1.5 text-sm font-medium">Ion source<Input value={draft.ion_source} onChange={(event) => setDraft((current) => ({ ...current, ion_source: event.target.value }))} /></label>
                {editingId ? <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.active} onChange={(event) => setDraft((current) => ({ ...current, active: event.target.checked }))} /> Active for new acquisition worklists</label> : null}
                {availableInstruments.length === 0 ? <p className="rounded-md bg-muted p-3 text-sm text-muted-foreground">No active instruments are registered for this facility. An administrator must register its LC and MS instruments first.</p> : null}
                <div className="flex flex-wrap gap-2"><Button type="submit" disabled={saveMutation.isPending || !draft.facility}>{saveMutation.isPending ? "Saving…" : editingId ? "Save LC-MS setup" : "Add LC-MS setup"}</Button>{editingId ? <Button type="button" variant="secondary" onClick={() => { setEditingId(null); setDraft(emptyDraft); }}>Cancel edit</Button> : null}</div>
              </form>
            ) : <p className="text-sm text-muted-foreground">No facility is available in your access scope.</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Managed setups</CardTitle><CardDescription>Active setups are available to the worklist builder. New configurations are saved with acquisitions.</CardDescription></CardHeader>
          <CardContent className="grid gap-3">
            {configurationsQuery.isLoading ? <p className="text-sm text-muted-foreground">Loading setups…</p> : configurations.length ? configurations.map((configuration) => {
              const lc = instrumentById.get(String(configuration.lc_instrument));
              const ms = instrumentById.get(String(configuration.ms_instrument));
              return <div key={configuration.id} className="grid min-w-0 gap-3 rounded-lg border p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                <div className="min-w-0"><div className="break-words font-semibold">{configuration.name}</div><div className="mt-1 break-words text-sm text-muted-foreground">{configuration.method_name || "Method name missing"} · {configuration.active ? "Active" : "Inactive"}</div><div className="mt-2 grid gap-1 break-words text-xs text-muted-foreground"><span>LC: {lc?.nickname ?? "Not assigned"}{configuration.column_description ? ` · ${configuration.column_description}` : ""}</span><span>MS: {ms?.nickname ?? "Not assigned"}</span>{configuration.gradient_description ? <span>Gradient: {configuration.gradient_description}</span> : null}</div></div>
                <Button type="button" variant="secondary" size="sm" onClick={() => editConfiguration(configuration)}>Edit</Button>
              </div>;
            }) : <p className="text-sm text-muted-foreground">No LC-MS setups are configured yet.</p>}
            {configurationsQuery.isError ? <p role="alert" className="text-sm text-destructive">{configurationsQuery.error.message}</p> : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function WatcherMsAssignment({
  agent,
  instruments,
  canEdit,
  onSaved,
}: {
  agent: { id: number | string; name: string; ms_instrument: number | string | null; ms_instrument_name: string | null; active: boolean };
  instruments: Array<{ id: number | string; nickname: string; instrument_type: string; active: boolean }>;
  canEdit: boolean;
  onSaved: () => void;
}) {
  const [instrumentId, setInstrumentId] = useState(agent.ms_instrument ? String(agent.ms_instrument) : none);
  const mutation = useMutation({ mutationFn: () => updateAcquisitionAgent(Number(agent.id), { ms_instrument: instrumentId === none ? null : Number(instrumentId) }), onSuccess: onSaved });
  const msInstruments = instruments.filter((instrument) => instrument.instrument_type === "ms" || instrument.instrument_type === "lcms");

  return (
    <div className="grid min-w-0 gap-3 rounded-lg border p-4 sm:grid-cols-[minmax(0,1fr)_minmax(12rem,auto)_auto] sm:items-center">
      <div className="min-w-0"><div className="break-words font-semibold">{agent.name}</div><div className="text-xs text-muted-foreground">{agent.active ? "Active watcher" : "Inactive watcher"} · Current MS: {agent.ms_instrument_name || "Unassigned"}</div></div>
      {canEdit ? <select aria-label={`MS assigned to ${agent.name}`} className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={instrumentId} onChange={(event) => setInstrumentId(event.target.value)}><option value={none}>Unassigned</option>{msInstruments.map((instrument) => <option key={instrument.id} value={instrument.id}>{instrument.nickname}</option>)}</select> : <span className="text-sm text-muted-foreground">Admin managed</span>}
      {canEdit ? <Button type="button" variant="secondary" size="sm" disabled={mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? "Saving…" : "Save MS"}</Button> : null}
      {mutation.isError ? <p role="alert" className="text-sm text-destructive sm:col-span-3">{mutation.error.message}</p> : null}
    </div>
  );
}

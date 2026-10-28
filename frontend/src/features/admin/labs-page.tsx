import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AdminTabs } from "@/features/admin/admin-tabs";
import { createAdminOrganization, fetchAdminLabDirectory, queryKeys } from "@/lib/api/queries";

const emptyRecords = { universities: [], facilities: [], labs: [] } as const;

export default function AdminLabsPage() {
  const queryClient = useQueryClient();
  const directoryQuery = useQuery({ queryKey: queryKeys.adminLabDirectory(), queryFn: fetchAdminLabDirectory });
  const [universityName, setUniversityName] = useState("");
  const [abbreviation, setAbbreviation] = useState("");
  const [website, setWebsite] = useState("");
  const [facilityUniversity, setFacilityUniversity] = useState("");
  const [facilityName, setFacilityName] = useState("");
  const [facilitySlug, setFacilitySlug] = useState("");
  const [facilityEmail, setFacilityEmail] = useState("");
  const [labFacility, setLabFacility] = useState("");
  const [labName, setLabName] = useState("");
  const [labSlug, setLabSlug] = useState("");
  const [billingCode, setBillingCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const directory = directoryQuery.data ?? emptyRecords;
  const activeUniversities = useMemo(() => directory.universities.filter((university) => university.active), [directory.universities]);
  const activeFacilities = useMemo(() => directory.facilities.filter((facility) => facility.active), [directory.facilities]);

  useEffect(() => {
    if (!facilityUniversity && activeUniversities.length) setFacilityUniversity(String(activeUniversities[0].id));
  }, [facilityUniversity, activeUniversities]);
  useEffect(() => {
    if (!labFacility && activeFacilities.length) setLabFacility(String(activeFacilities[0].id));
  }, [labFacility, activeFacilities]);

  const createMutation = useMutation({
    mutationFn: createAdminOrganization,
    onSuccess: async (result) => {
      const recordName = String(result.record.name ?? "Record");
      setMessage(`${recordName} added. You can now continue with the next setup step or invite users.`);
      setError("");
      if (result.kind === "university") setUniversityName("");
      if (result.kind === "facility") setFacilityName("");
      if (result.kind === "lab") setLabName("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.adminLabDirectory() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.adminUserAccess() }),
      ]);
    },
    onError: (reason) => { setError(reason instanceof Error ? reason.message : "Could not add this organization record."); setMessage(""); },
  });

  function submit(event: FormEvent, payload: Record<string, string | number>) {
    event.preventDefault();
    setError("");
    setMessage("");
    createMutation.mutate(payload);
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Administration</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Organization setup</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">Set up the university, facility, and lab structure used to scope projects and user permissions.</p>
      </header>
      <AdminTabs />
      {error ? <div role="alert" className="break-words rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</div> : null}
      {message ? <div role="status" aria-live="polite" className="rounded-md border bg-secondary/40 px-4 py-3 text-sm">{message}</div> : null}

      <div className="grid items-start gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader><CardTitle>1. Add a university</CardTitle><CardDescription>Use the institutional parent for one or more facilities.</CardDescription></CardHeader>
          <CardContent>
            <form className="grid gap-3" onSubmit={(event) => submit(event, { kind: "university", name: universityName.trim(), abbreviation: abbreviation.trim(), website: website.trim() })}>
              <label className="grid gap-1.5 text-sm font-medium">University name<Input name="university_name" autoComplete="organization" required value={universityName} onChange={(event) => setUniversityName(event.target.value)} /></label>
              <label className="grid gap-1.5 text-sm font-medium">Abbreviation <span className="font-normal text-muted-foreground">Optional</span><Input name="university_abbreviation" spellCheck={false} value={abbreviation} onChange={(event) => setAbbreviation(event.target.value)} /></label>
              <label className="grid gap-1.5 text-sm font-medium">Website <span className="font-normal text-muted-foreground">Optional</span><Input name="university_website" type="url" autoComplete="url" placeholder="https://example.edu" value={website} onChange={(event) => setWebsite(event.target.value)} /></label>
              <Button type="submit" disabled={createMutation.isPending}>{createMutation.isPending ? "Adding…" : "Add university"}</Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>2. Add a facility</CardTitle><CardDescription>Facilities group shared instruments and lab spaces.</CardDescription></CardHeader>
          <CardContent>
            {activeUniversities.length === 0 ? <p className="text-sm text-muted-foreground">Add an active university first.</p> : (
              <form className="grid gap-3" onSubmit={(event) => submit(event, { kind: "facility", university: Number(facilityUniversity), name: facilityName.trim(), slug: facilitySlug.trim(), contact_email: facilityEmail.trim() })}>
                <label className="grid gap-1.5 text-sm font-medium">University<select name="facility_university" className="h-10 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={facilityUniversity} onChange={(event) => setFacilityUniversity(event.target.value)}>{activeUniversities.map((university) => <option key={university.id} value={university.id}>{university.name}</option>)}</select></label>
                <label className="grid gap-1.5 text-sm font-medium">Facility name<Input name="facility_name" required value={facilityName} onChange={(event) => setFacilityName(event.target.value)} /></label>
                <label className="grid gap-1.5 text-sm font-medium">URL slug <span className="font-normal text-muted-foreground">Optional; generated from name if blank</span><Input name="facility_slug" spellCheck={false} value={facilitySlug} onChange={(event) => setFacilitySlug(event.target.value)} /></label>
                <label className="grid gap-1.5 text-sm font-medium">Contact email <span className="font-normal text-muted-foreground">Optional</span><Input name="facility_email" type="email" autoComplete="email" spellCheck={false} value={facilityEmail} onChange={(event) => setFacilityEmail(event.target.value)} /></label>
                <Button type="submit" disabled={createMutation.isPending}>{createMutation.isPending ? "Adding…" : "Add facility"}</Button>
              </form>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>3. Add a lab</CardTitle><CardDescription>After creation, invite users from the Users tab and grant their lab roles.</CardDescription></CardHeader>
          <CardContent>
            {activeFacilities.length === 0 ? <p className="text-sm text-muted-foreground">Add an active facility first.</p> : (
              <form className="grid gap-3" onSubmit={(event) => submit(event, { kind: "lab", facility: Number(labFacility), name: labName.trim(), slug: labSlug.trim(), billing_code: billingCode.trim() })}>
                <label className="grid gap-1.5 text-sm font-medium">Facility<select name="lab_facility" className="h-10 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={labFacility} onChange={(event) => setLabFacility(event.target.value)}>{activeFacilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.name} · {facility.university_name}</option>)}</select></label>
                <label className="grid gap-1.5 text-sm font-medium">Lab name<Input name="lab_name" required value={labName} onChange={(event) => setLabName(event.target.value)} /></label>
                <label className="grid gap-1.5 text-sm font-medium">URL slug <span className="font-normal text-muted-foreground">Optional; generated from name if blank</span><Input name="lab_slug" spellCheck={false} value={labSlug} onChange={(event) => setLabSlug(event.target.value)} /></label>
                <label className="grid gap-1.5 text-sm font-medium">Billing code <span className="font-normal text-muted-foreground">Optional</span><Input name="lab_billing_code" spellCheck={false} value={billingCode} onChange={(event) => setBillingCode(event.target.value)} /></label>
                <Button type="submit" disabled={createMutation.isPending}>{createMutation.isPending ? "Adding…" : "Add lab"}</Button>
              </form>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Existing labs</CardTitle><CardDescription>Lab membership counts help you confirm the access scope before inviting users.</CardDescription></CardHeader>
        <CardContent className="p-0">
          {directoryQuery.isLoading ? <p className="p-5 text-sm text-muted-foreground">Loading organization directory…</p> : directoryQuery.isError ? <p role="alert" className="p-5 text-sm text-destructive">{directoryQuery.error.message}</p> : directory.labs.length === 0 ? <p className="p-5 text-sm text-muted-foreground">No labs yet. Add the first lab above.</p> : (
            <ul className="divide-y">
              {directory.labs.map((lab) => (
                <li key={lab.id} className="grid gap-1 px-5 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                  <div className="min-w-0"><div className="truncate text-sm font-medium">{lab.name}</div><div className="truncate text-xs text-muted-foreground">{lab.facility_name} · {lab.university_name} · {lab.slug}</div></div>
                  <div className="text-xs text-muted-foreground">{lab.active ? "Active" : "Inactive"} · {lab.active_member_count} active member{lab.active_member_count === 1 ? "" : "s"}</div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, ClipboardList, Send } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { PageHero } from "@/components/layout/page-section";
import { Breadcrumbs } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { createIntakeRequest, fetchCurrentUser, queryKeys, type IntakeRequestCreatePayload } from "@/lib/api/queries";
import { queryClient } from "@/lib/api/query-client";

const steps = ["Lab", "Study", "Billing", "Review"];

export default function SubmissionWizardPage() {
  const navigate = useNavigate();
  const currentUserQuery = useQuery({
    queryKey: queryKeys.currentUser(),
    queryFn: fetchCurrentUser,
  });
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [selectedLabId, setSelectedLabId] = useState("");
  const [form, setForm] = useState({
    requested_title: "",
    requested_code: "",
    objective: "",
    sample_count_estimate: 24,
    acquisition_deadline: "",
    institution_name: "",
    contact_name: "",
    contact_email: "",
    invoice_email: "",
    organism: "",
    matrix: "",
    plate_format: "96" as "96" | "384",
    plate_layout: "",
    shipping_expectations: "",
    hazards_notes: "",
    billing_po_reference: "",
    billing_address: "",
  });

  const defaultLabId = currentUserQuery.data?.labs?.[0]?.id ? String(currentUserQuery.data.labs[0].id) : "";
  const labId = selectedLabId || defaultLabId;
  const labs = currentUserQuery.data?.labs ?? [];
  const currentStepComplete = isStepComplete(step, form, labId);
  const formComplete = steps.every((_, index) => isStepComplete(index, form, labId));

  const createMutation = useMutation({
    mutationFn: createIntakeRequest,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.intakeRequests() });
      navigate("/submissions");
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Could not submit intake request.");
    },
  });

  const metadata = useMemo(
    () => ({
      schema_version: "2026-08-03",
      institution: {
        name: form.institution_name,
      },
      contact: {
        name: form.contact_name,
        email: form.contact_email,
      },
      sample_planning: {
        organism: form.organism,
        matrix: form.matrix,
        sample_count: form.sample_count_estimate,
        plate_format: form.plate_format,
        plate_layout: form.plate_layout,
      },
      shipping: {
        expectations: form.shipping_expectations,
      },
      billing: {
        invoice_email: form.invoice_email,
        po_reference: form.billing_po_reference,
        billing_address: form.billing_address ? { raw: form.billing_address } : {},
      },
      hazards: {
        handling_notes: form.hazards_notes,
      },
      notes: "",
    }),
    [form],
  );

  function submit() {
    setError("");
    if (!formComplete) {
      setError("Complete every required field before submitting.");
      return;
    }
    const payload: IntakeRequestCreatePayload = {
      lab: Number(labId),
      requested_title: form.requested_title,
      requested_code: form.requested_code,
      objective: form.objective,
      sample_count_estimate: form.sample_count_estimate,
      acquisition_deadline: form.acquisition_deadline || null,
      institution_name: form.institution_name,
      contact_name: form.contact_name,
      contact_email: form.contact_email,
      invoice_email: form.invoice_email,
      organism: form.organism,
      matrix: form.matrix,
      plate_format: form.plate_format,
      shipping_notes: form.shipping_expectations,
      hazards_notes: form.hazards_notes,
      metadata,
    };
    createMutation.mutate(payload);
  }

  return (
    <div className="grid gap-4">
      <Breadcrumbs items={[{ label: "Submissions", href: "/submissions" }, { label: "New request" }]} />
      <PageHero
        eyebrow="Collaborator intake"
        title="Submit a request"
        description="Capture the minimum operational details needed for plate planning, billing, shipping, and review."
        actions={
          <Button asChild variant="secondary">
            <Link to="/submissions">
              <ClipboardList className="h-4 w-4" />
              My submissions
            </Link>
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>Request wizard</CardTitle>
          <CardDescription>Four short steps. Save and submit when the requested scope is complete.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="flex flex-wrap gap-2">
            {steps.map((label, index) => (
              <div
                key={label}
                className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                  index === step ? "border-primary bg-primary text-primary-foreground" : "bg-secondary/50"
                }`}
              >
                {index + 1}. {label}
              </div>
            ))}
          </div>

            {step === 0 ? (
            <section className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-2 text-sm font-medium md:col-span-2">
                Target lab *
                <Select value={labId} onValueChange={setSelectedLabId}>
                  <SelectTrigger>
                    <SelectValue placeholder={labs.length ? "Select a lab" : "No labs available"} />
                  </SelectTrigger>
                  <SelectContent>
                    {labs.map((lab) => (
                      <SelectItem key={lab.id} value={String(lab.id)}>
                        {lab.name} · {lab.facility_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <Field label="Project title" value={form.requested_title} onChange={(value) => setForm((current) => ({ ...current, requested_title: value }))} required />
              <Field label="Project code" value={form.requested_code} onChange={(value) => setForm((current) => ({ ...current, requested_code: value }))} required />
              <label className="grid gap-2 text-sm font-medium md:col-span-2">
                Objective *
                <Textarea rows={5} value={form.objective} onChange={(event) => setForm((current) => ({ ...current, objective: event.target.value }))} />
              </label>
            </section>
          ) : null}

          {step === 1 ? (
            <section className="grid gap-3 md:grid-cols-2">
              <Field label="Institution" value={form.institution_name} onChange={(value) => setForm((current) => ({ ...current, institution_name: value }))} required />
              <Field label="PI or contact name" value={form.contact_name} onChange={(value) => setForm((current) => ({ ...current, contact_name: value }))} required />
              <Field label="Contact email" value={form.contact_email} onChange={(value) => setForm((current) => ({ ...current, contact_email: value }))} required />
              <Field label="Sample count" type="number" value={String(form.sample_count_estimate)} onChange={(value) => setForm((current) => ({ ...current, sample_count_estimate: Number(value) || 0 }))} required />
              <Field label="Organism" value={form.organism} onChange={(value) => setForm((current) => ({ ...current, organism: value }))} required />
              <Field label="Matrix" value={form.matrix} onChange={(value) => setForm((current) => ({ ...current, matrix: value }))} required />
            </section>
          ) : null}

          {step === 2 ? (
            <section className="grid gap-3 md:grid-cols-2">
              <Field label="Invoice email" value={form.invoice_email} onChange={(value) => setForm((current) => ({ ...current, invoice_email: value }))} required />
              <Field label="PO or reference" value={form.billing_po_reference} onChange={(value) => setForm((current) => ({ ...current, billing_po_reference: value }))} />
              <label className="grid gap-2 text-sm font-medium">
                Plate format
                <Select value={form.plate_format} onValueChange={(value) => setForm((current) => ({ ...current, plate_format: value as "96" | "384" }))}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="96">96-well</SelectItem>
                    <SelectItem value="384">384-well</SelectItem>
                  </SelectContent>
                </Select>
              </label>
              <Field label="Acquisition deadline" type="date" value={form.acquisition_deadline} onChange={(value) => setForm((current) => ({ ...current, acquisition_deadline: value }))} />
              <label className="grid gap-2 text-sm font-medium md:col-span-2">
                Shipping expectations
                <Textarea rows={3} value={form.shipping_expectations} onChange={(event) => setForm((current) => ({ ...current, shipping_expectations: event.target.value }))} />
              </label>
              <label className="grid gap-2 text-sm font-medium md:col-span-2">
                Hazards or handling notes
                <Textarea rows={3} value={form.hazards_notes} onChange={(event) => setForm((current) => ({ ...current, hazards_notes: event.target.value }))} />
              </label>
            </section>
          ) : null}

          {step === 3 ? (
            <section className="grid gap-3 rounded-2xl border bg-secondary/20 p-4 text-sm">
              <ReviewRow label="Lab" value={labs.find((lab) => String(lab.id) === labId)?.name ?? "Not selected"} />
              <ReviewRow label="Project title" value={form.requested_title || "-"} />
              <ReviewRow label="Institution" value={form.institution_name || "-"} />
              <ReviewRow label="Sample count" value={String(form.sample_count_estimate)} />
              <ReviewRow label="Billing email" value={form.invoice_email || "-"} />
              <ReviewRow label="Plate format" value={form.plate_format} />
            </section>
          ) : null}

          {error ? <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</div> : null}

          <div className="flex flex-wrap justify-between gap-3 border-t pt-4">
            <Button type="button" variant="secondary" disabled={step === 0} onClick={() => setStep((current) => Math.max(0, current - 1))}>
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            <div className="flex gap-2">
              {step < steps.length - 1 ? (
              <Button type="button" disabled={!currentStepComplete} onClick={() => setStep((current) => Math.min(steps.length - 1, current + 1))}>
                  Next
                  <ArrowRight className="h-4 w-4" />
                </Button>
              ) : (
                <Button type="button" onClick={submit} disabled={createMutation.isPending || !formComplete}>
                  <Send className="h-4 w-4" />
                  {createMutation.isPending ? "Submitting..." : "Submit request"}
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
}) {
  return (
    <label className="grid gap-2 text-sm font-medium">
      <span>
        {label}
        {required ? " *" : ""}
      </span>
      <Input type={type} value={value} required={required} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function isStepComplete(step: number, form: Record<string, string | number>, labId: string) {
  const hasText = (value: unknown) => typeof value === "string" && value.trim().length > 0;
  switch (step) {
    case 0:
      return Boolean(labId) && hasText(form.requested_title) && hasText(form.requested_code) && hasText(form.objective);
    case 1:
      return (
        hasText(form.institution_name) &&
        hasText(form.contact_name) &&
        hasText(form.contact_email) &&
        Number(form.sample_count_estimate) > 0 &&
        hasText(form.organism) &&
        hasText(form.matrix)
      );
    case 2:
      return hasText(form.invoice_email);
    case 3:
      return true;
    default:
      return false;
  }
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-dashed pb-2 last:border-0 last:pb-0">
      <div className="font-semibold text-muted-foreground">{label}</div>
      <div className="max-w-[60%] text-right font-medium">{value}</div>
    </div>
  );
}

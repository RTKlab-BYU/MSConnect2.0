from math import log2
from statistics import median

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, FormView, ListView, TemplateView

from core.models import (
    AcquisitionWorklist,
    IntakeRequestStatus,
    Lab,
    LabMembership,
    ProcessingJob,
    ProcessingNode,
    ProcessingPipeline,
    ProcessingStatus,
    Project,
    ProjectIntakeRequest,
    ProjectStatus,
    ProteinQuant,
    RawFile,
    RunFileRole,
    Sample,
    UserRole,
    WorklistEntry,
)
from core.permissions import active_lab_ids, is_admin, user_role

from .forms import IntakeReviewForm, ProjectIntakeRequestForm


class IntakeLabScopeMixin:
    def allowed_lab_ids(self):
        if is_admin(self.request.user):
            return set(Lab.objects.values_list("id", flat=True))
        return set(active_lab_ids(self.request.user))

    def can_review_lab(self, lab_id: int) -> bool:
        if is_admin(self.request.user):
            return True
        if lab_id not in self.allowed_lab_ids():
            return False
        return (
            user_role(self.request.user) == UserRole.PI
            or LabMembership.objects.filter(
                user=self.request.user,
                lab_id=lab_id,
                active=True,
                role=UserRole.PI,
            ).exists()
            or Lab.objects.filter(id=lab_id, pi=self.request.user).exists()
        )


class IntakeCreateView(LoginRequiredMixin, IntakeLabScopeMixin, FormView):
    template_name = "ui/intake/new.html"
    form_class = ProjectIntakeRequestForm

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["lab"].queryset = Lab.objects.filter(id__in=self.allowed_lab_ids()).order_by("name")
        form.fields["requested_pi"].required = False
        return form

    def form_valid(self, form):
        intake = form.save(commit=False)
        if intake.lab_id not in self.allowed_lab_ids():
            return HttpResponseForbidden("Lab access denied")
        intake.submitted_by = self.request.user
        intake.save()
        messages.success(self.request, "Intake request submitted.")
        return redirect("ui:intake_detail", pk=intake.pk)


class IntakeListView(LoginRequiredMixin, IntakeLabScopeMixin, ListView):
    template_name = "ui/intake/list.html"
    model = ProjectIntakeRequest
    context_object_name = "intake_requests"

    def get_queryset(self):
        queryset = ProjectIntakeRequest.objects.select_related("lab", "submitted_by", "reviewed_by", "promoted_project")
        if not is_admin(self.request.user):
            queryset = queryset.filter(lab_id__in=self.allowed_lab_ids())

        status_value = self.request.GET.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)

        lab_value = self.request.GET.get("lab")
        if lab_value:
            queryset = queryset.filter(lab_id=lab_value)

        submitter_value = self.request.GET.get("submitter")
        if submitter_value:
            queryset = queryset.filter(submitted_by_id=submitter_value)

        start_date = self.request.GET.get("start_date")
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)

        ordering = self.request.GET.get("ordering", "-updated_at")
        allowed_ordering = {
            "updated_at",
            "-updated_at",
            "created_at",
            "-created_at",
            "requested_title",
            "-requested_title",
        }
        if ordering not in allowed_ordering:
            ordering = "-updated_at"

        return queryset.order_by(ordering, "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuses"] = IntakeRequestStatus.choices
        context["labs"] = Lab.objects.filter(id__in=self.allowed_lab_ids()).order_by("name")
        context["filters"] = self.request.GET
        return context


class IntakeDetailView(LoginRequiredMixin, IntakeLabScopeMixin, DetailView):
    template_name = "ui/intake/detail.html"
    model = ProjectIntakeRequest
    context_object_name = "intake"

    def get_queryset(self):
        queryset = ProjectIntakeRequest.objects.select_related(
            "lab",
            "submitted_by",
            "reviewed_by",
            "promoted_project",
        )
        if is_admin(self.request.user):
            return queryset
        return queryset.filter(lab_id__in=self.allowed_lab_ids())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_review"] = self.can_review_lab(self.object.lab_id)
        context["review_form"] = IntakeReviewForm(initial={"status": IntakeRequestStatus.IN_REVIEW})
        return context


class IntakeReviewView(LoginRequiredMixin, IntakeLabScopeMixin, FormView):
    form_class = IntakeReviewForm

    def post(self, request, *args, **kwargs):
        self.intake = get_object_or_404(ProjectIntakeRequest, pk=self.kwargs["pk"])
        if not self.can_review_lab(self.intake.lab_id):
            return HttpResponseForbidden("Review access denied")
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        action = self.request.POST.get("action")
        if action == "promote":
            try:
                project = self.intake.promote_to_project()
                messages.success(self.request, f"Promoted to project {project.code}.")
            except DjangoValidationError as exc:
                messages.error(self.request, exc.message)
            return redirect("ui:intake_detail", pk=self.intake.pk)

        try:
            self.intake.transition_to(
                new_status=form.cleaned_data["status"],
                reviewer=self.request.user,
                note=form.cleaned_data["review_note"],
            )
            messages.success(self.request, "Review state updated.")
        except DjangoValidationError as exc:
            messages.error(self.request, exc.message)
        return redirect("ui:intake_detail", pk=self.intake.pk)


class PreAcquisitionProjectListView(LoginRequiredMixin, IntakeLabScopeMixin, ListView):
    template_name = "ui/projects/pre_acq.html"
    model = ProjectIntakeRequest
    context_object_name = "approved_requests"

    def get_queryset(self):
        queryset = ProjectIntakeRequest.objects.select_related("lab", "submitted_by", "promoted_project").filter(
            status=IntakeRequestStatus.APPROVED
        )
        if is_admin(self.request.user):
            return queryset.order_by("-updated_at")
        return queryset.filter(lab_id__in=self.allowed_lab_ids()).order_by("-updated_at")


class ShowcaseScopeMixin(IntakeLabScopeMixin):
    def scoped_worklists(self):
        queryset = AcquisitionWorklist.objects.select_related(
            "experiment",
            "experiment__project",
            "experiment__project__lab",
            "configuration",
        )
        if is_admin(self.request.user):
            return queryset
        return queryset.filter(experiment__project__lab_id__in=self.allowed_lab_ids())

    def scoped_projects(self):
        queryset = Project.objects.select_related("lab", "pi")
        if is_admin(self.request.user):
            return queryset
        return queryset.filter(lab_id__in=self.allowed_lab_ids())

    def selected_worklist(self, pk=None):
        queryset = self.scoped_worklists()
        if pk:
            return queryset.filter(pk=pk).first()
        return queryset.filter(experiment__project__code="COHORT-DIA-100").first() or queryset.first()

    def workflow_context(self, worklist):
        entries = (
            WorklistEntry.objects.filter(worklist=worklist).select_related("run", "run__sample") if worklist else []
        )
        run_ids = [entry.run_id for entry in entries]
        raw_files = RawFile.objects.filter(run_id__in=run_ids).select_related("run", "run__sample")
        jobs = ProcessingJob.objects.filter(run_id__in=run_ids).select_related("run", "raw_file", "pipeline")
        return {
            "worklist": worklist,
            "entries": entries,
            "run_ids": run_ids,
            "raw_files": raw_files,
            "jobs": jobs,
            "project": worklist.experiment.project if worklist else None,
            "pipeline": ProcessingPipeline.objects.filter(name="DIA-NN").first(),
            "nodes": ProcessingNode.objects.filter(node_type="diann").order_by("name"),
        }

    def qc_pair_stats(self, worklist):
        if not worklist:
            return []

        ideal = {
            "Homo sapiens": {"a": 0.65, "b": 0.65},
            "Saccharomyces cerevisiae": {"a": 0.30, "b": 0.15},
            "Escherichia coli": {"a": 0.05, "b": 0.20},
        }
        labels = (
            worklist.entries.filter(file_role=RunFileRole.QC)
            .exclude(hye_pair_label="")
            .values_list("hye_pair_label", flat=True)
            .distinct()
            .order_by("hye_pair_label")
        )
        pair_rows = []
        for label in labels:
            entries = {
                entry.run.sample.name: entry
                for entry in worklist.entries.select_related("run", "run__sample").filter(hye_pair_label=label)
            }
            a_entry = entries.get("HYE-A")
            b_entry = entries.get("HYE-B")
            a_job = self._complete_job(a_entry)
            b_job = self._complete_job(b_entry)
            organism_rows = []

            for organism, target in ideal.items():
                a_values = self._quant_values_by_accession(a_job, organism)
                b_values = self._quant_values_by_accession(b_job, organism)
                shared_accessions = sorted(set(a_values).intersection(b_values))
                a_log2 = [log2(a_values[accession]) for accession in shared_accessions if a_values[accession] > 0]
                b_log2 = [log2(b_values[accession]) for accession in shared_accessions if b_values[accession] > 0]
                median_a = round(median(a_log2), 2) if a_log2 else None
                median_b = round(median(b_log2), 2) if b_log2 else None
                observed_ratio = round(2 ** (median_b - median_a), 2) if median_a and median_b else None
                ideal_ratio = round(target["b"] / target["a"], 2)
                organism_rows.append(
                    {
                        "organism": organism,
                        "shared_n": len(shared_accessions),
                        "median_log2_a": median_a,
                        "median_log2_b": median_b,
                        "observed_ratio": observed_ratio,
                        "ideal_a": target["a"],
                        "ideal_b": target["b"],
                        "ideal_ratio": ideal_ratio,
                    }
                )

            pair_rows.append(
                {
                    "label": label,
                    "a_entry": a_entry,
                    "b_entry": b_entry,
                    "a_raw_file": a_entry.matched_raw_file if a_entry else None,
                    "b_raw_file": b_entry.matched_raw_file if b_entry else None,
                    "organisms": organism_rows,
                    "shared_total_n": sum(row["shared_n"] for row in organism_rows),
                }
            )
        return pair_rows

    def _complete_job(self, entry):
        if not entry:
            return None
        return ProcessingJob.objects.filter(run=entry.run, status=ProcessingStatus.COMPLETE).first()

    def _quant_values_by_accession(self, job, organism):
        if not job:
            return {}
        return {
            quant.protein.accession: quant.value
            for quant in ProteinQuant.objects.filter(job=job, protein__organism=organism).select_related("protein")
        }


class ProjectListView(LoginRequiredMixin, ShowcaseScopeMixin, ListView):
    template_name = "ui/projects/list.html"
    model = Project
    context_object_name = "projects"

    def get_queryset(self):
        queryset = self.scoped_projects().annotate(
            experiment_count=Count("experiments", distinct=True),
            sample_count=Count("experiments__samples", distinct=True),
            acquisition_count=Count("experiments__worklists", distinct=True),
            run_count=Count("experiments__samples__runs", distinct=True),
            raw_file_count=Count("experiments__samples__runs__raw_files", distinct=True),
            processing_job_count=Count("experiments__samples__runs__processing_jobs", distinct=True),
        )

        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(title__icontains=search)
                | Q(lab__name__icontains=search)
                | Q(pi__username__icontains=search)
            )

        status_value = self.request.GET.get("status", "").strip()
        if status_value:
            queryset = queryset.filter(status=status_value)

        return queryset.order_by("lab__name", "code")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projects = context["projects"]
        context.update(
            {
                "filters": self.request.GET,
                "statuses": ProjectStatus.choices,
                "total_projects": projects.count(),
                "total_samples": sum(project.sample_count for project in projects),
                "total_acquisitions": sum(project.acquisition_count for project in projects),
                "total_raw_files": sum(project.raw_file_count for project in projects),
            }
        )
        return context


class ProjectDetailView(LoginRequiredMixin, ShowcaseScopeMixin, DetailView):
    template_name = "ui/projects/detail.html"
    model = Project
    context_object_name = "project"

    def get_queryset(self):
        return self.scoped_projects().annotate(
            experiment_count=Count("experiments", distinct=True),
            sample_count=Count("experiments__samples", distinct=True),
            acquisition_count=Count("experiments__worklists", distinct=True),
            run_count=Count("experiments__samples__runs", distinct=True),
            raw_file_count=Count("experiments__samples__runs__raw_files", distinct=True),
            processing_job_count=Count("experiments__samples__runs__processing_jobs", distinct=True),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        worklists = (
            AcquisitionWorklist.objects.filter(experiment__project=project)
            .select_related("experiment", "configuration")
            .annotate(
                entry_count=Count("entries", distinct=True),
                matched_file_count=Count("entries__run__raw_files", distinct=True),
                sample_run_count=Count("entries__run", filter=Q(entries__file_role=RunFileRole.SAMPLE), distinct=True),
                qc_run_count=Count("entries__run", filter=Q(entries__file_role=RunFileRole.QC), distinct=True),
            )
            .order_by("-updated_at", "name")
        )
        samples = (
            Sample.objects.filter(experiment__project=project)
            .select_related("experiment", "submitted_by")
            .annotate(
                run_count=Count("runs", distinct=True),
                raw_file_count=Count("runs__raw_files", distinct=True),
                processing_job_count=Count("runs__processing_jobs", distinct=True),
            )
            .order_by("experiment__name", "name")
        )
        latest_raw_files = (
            RawFile.objects.filter(run__sample__experiment__project=project)
            .select_related("run", "run__sample")
            .order_by("-imported_at", "-updated_at")[:8]
        )
        missing_upload_count = sum(max(worklist.entry_count - worklist.matched_file_count, 0) for worklist in worklists)
        first_worklist = worklists.first()

        context.update(
            {
                "worklists": worklists,
                "samples": samples,
                "latest_raw_files": latest_raw_files,
                "missing_upload_count": missing_upload_count,
                "first_worklist": first_worklist,
            }
        )
        return context


class ShowcaseDashboardView(LoginRequiredMixin, ShowcaseScopeMixin, TemplateView):
    template_name = "ui/showcase/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worklist = self.selected_worklist()
        workflow = self.workflow_context(worklist)
        entries = workflow["entries"]
        raw_files = workflow["raw_files"]
        jobs = workflow["jobs"]

        context.update(
            {
                "project": workflow["project"],
                "worklist": worklist,
                "entry_count": entries.count(),
                "matched_file_count": raw_files.count(),
                "missing_file_count": max(entries.count() - raw_files.count(), 0),
                "job_counts": jobs.values("status").annotate(count=Count("id")).order_by("status"),
                "node": ProcessingNode.objects.filter(node_type="diann").first(),
                "pipeline": workflow["pipeline"],
                "qc_pairs": self.qc_pair_stats(worklist),
                "unmatched_raw_files": RawFile.objects.filter(run__isnull=True).order_by("-imported_at")[:5],
            }
        )
        return context


class ExperimentalDesignView(LoginRequiredMixin, ShowcaseScopeMixin, TemplateView):
    template_name = "ui/showcase/design.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worklist = self.selected_worklist()
        workflow = self.workflow_context(worklist)
        entries = workflow["entries"]
        context.update(
            workflow
            | {
                "sample_entries": entries.filter(file_role=RunFileRole.SAMPLE),
                "qc_entries": entries.filter(file_role=RunFileRole.QC),
                "library_entries": entries.filter(file_role=RunFileRole.LIBRARY),
                "blank_entries": entries.filter(file_role__in=(RunFileRole.BLANK, RunFileRole.WASH)),
                "qc_pairs": self.qc_pair_stats(worklist),
                "healthy_sample_count": entries.filter(run__sample__metadata__condition="healthy").count(),
                "diseased_sample_count": entries.filter(run__sample__metadata__condition="diseased").count(),
            }
        )
        return context


class AcquisitionMonitorView(LoginRequiredMixin, ShowcaseScopeMixin, TemplateView):
    template_name = "ui/showcase/acquisition.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worklist = self.selected_worklist(self.kwargs.get("pk"))
        workflow = self.workflow_context(worklist)
        entries = (
            worklist.entries.select_related("run", "run__sample")
            .prefetch_related("run__raw_files")
            .order_by("position")
            if worklist
            else []
        )
        context.update(
            workflow
            | {
                "entries": entries,
                "unmatched_raw_files": RawFile.objects.filter(run__isnull=True).order_by("-imported_at"),
                "watcher": {
                    "incoming_root": "/data/incoming",
                    "storage_root": "/data/raw",
                    "mode": "recursive file watcher",
                    "matching": "expected filename + worklist position",
                },
            }
        )
        return context


class ResultsTelemetryView(LoginRequiredMixin, ShowcaseScopeMixin, TemplateView):
    template_name = "ui/showcase/results.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worklist = self.selected_worklist(self.kwargs.get("pk"))
        workflow = self.workflow_context(worklist)
        result_rows = []
        for job in workflow["jobs"].order_by("run__worklist_position"):
            protein_count = ProteinQuant.objects.filter(job=job).values("protein_id").distinct().count()
            peptide_count = job.peptide_quants.values("peptide_id").distinct().count()
            raw_telemetry = job.raw_file.metadata.get("lc_ms_telemetry", {}) if job.raw_file_id else {}
            job_telemetry = job.metadata.get("telemetry", {})
            result_rows.append(
                {
                    "job": job,
                    "protein_count": protein_count,
                    "peptide_count": peptide_count,
                    "raw_telemetry": raw_telemetry,
                    "job_telemetry": job_telemetry,
                }
            )
        context.update(workflow | {"result_rows": result_rows})
        return context


class WorklistDetailView(LoginRequiredMixin, ShowcaseScopeMixin, DetailView):
    template_name = "ui/showcase/worklist_detail.html"
    model = AcquisitionWorklist
    context_object_name = "worklist"

    def get_queryset(self):
        return self.scoped_worklists()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = (
            self.object.entries.select_related("run", "run__sample")
            .prefetch_related("run__raw_files", "run__processing_jobs")
            .order_by("position")
        )
        context["entries"] = entries
        context["unmatched_raw_files"] = RawFile.objects.filter(run__isnull=True).order_by("-imported_at")
        return context


class ProcessingOverviewView(LoginRequiredMixin, ShowcaseScopeMixin, TemplateView):
    template_name = "ui/showcase/processing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worklist = self.selected_worklist(self.kwargs.get("pk"))
        runs = list(worklist.entries.values_list("run_id", flat=True)) if worklist else []
        context.update(
            {
                "worklist": worklist,
                "pipeline": ProcessingPipeline.objects.filter(name="DIA-NN").first(),
                "nodes": ProcessingNode.objects.filter(node_type="diann").order_by("name"),
                "jobs": ProcessingJob.objects.filter(run_id__in=runs)
                .select_related("run", "raw_file", "pipeline")
                .order_by("run__worklist_position"),
                "job_counts": ProcessingJob.objects.filter(run_id__in=runs)
                .values("status")
                .annotate(count=Count("id"))
                .order_by("status"),
                "queued_or_running": ProcessingJob.objects.filter(
                    run_id__in=runs,
                    status__in=(ProcessingStatus.QUEUED, ProcessingStatus.RUNNING),
                ).count(),
            }
        )
        return context


class QCDashboardView(LoginRequiredMixin, ShowcaseScopeMixin, TemplateView):
    template_name = "ui/showcase/qc_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worklist = self.selected_worklist(self.kwargs.get("pk"))
        context.update({"worklist": worklist, "pairs": self.qc_pair_stats(worklist)})
        return context

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, FormView, ListView

from core.models import IntakeRequestStatus, Lab, LabMembership, ProjectIntakeRequest, UserRole
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

from django import forms

from core.models import IntakeRequestStatus, ProjectIntakeRequest


class ProjectIntakeRequestForm(forms.ModelForm):
    class Meta:
        model = ProjectIntakeRequest
        fields = (
            "lab",
            "requested_title",
            "requested_code",
            "requested_pi",
            "objective",
            "sample_count_estimate",
            "acquisition_deadline",
        )


class IntakeReviewForm(forms.Form):
    status = forms.ChoiceField(
        choices=(
            (IntakeRequestStatus.IN_REVIEW, "In Review"),
            (IntakeRequestStatus.APPROVED, "Approved"),
            (IntakeRequestStatus.REJECTED, "Rejected"),
        )
    )
    review_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

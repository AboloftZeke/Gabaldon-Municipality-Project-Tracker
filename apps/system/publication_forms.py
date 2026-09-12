from django import forms

from .publication_workflow import PublicationStatus


class PublicationReviewForm(forms.Form):
    decision = forms.ChoiceField(
        choices=(
            (PublicationStatus.APPROVED, 'Approve'),
            (PublicationStatus.NEEDS_REVISION, 'Request Revisions'),
            (PublicationStatus.REJECTED, 'Reject'),
        ),
        widget=forms.RadioSelect,
    )
    notes = forms.CharField(
        required=False,
        label='Review notes',
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': (
                'Explain required changes or the reason for rejection.'
            ),
        }),
    )

    def clean(self):
        cleaned_data = super().clean()
        decision = cleaned_data.get('decision')
        notes = (cleaned_data.get('notes') or '').strip()
        if decision in {
            PublicationStatus.NEEDS_REVISION,
            PublicationStatus.REJECTED,
        } and not notes:
            self.add_error(
                'notes',
                'Review notes are required for this decision.',
            )
        cleaned_data['notes'] = notes
        return cleaned_data

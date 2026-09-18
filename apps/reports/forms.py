from django import forms

from .services import disclosed_projects_for_report


class IndividualProjectReportRequestForm(forms.Form):
    project_id = forms.TypedChoiceField(
        label='Project',
        coerce=int,
        empty_value=None,
    )

    def __init__(self, *args, report_type, **kwargs):
        super().__init__(*args, **kwargs)
        projects = disclosed_projects_for_report(report_type)
        self.fields['project_id'].choices = [
            ('', 'Select a disclosed project'),
            *[
                (project['record_id'], f"{project['code']} — {project['title']}")
                for project in projects
            ],
        ]


class BaseSummaryReportFilterForm(forms.Form):
    barangay = forms.ChoiceField(required=False)
    category = forms.ChoiceField(required=False)
    status = forms.ChoiceField(required=False)
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    report_type = None
    date_field_label = 'Date'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.projects = disclosed_projects_for_report(self.report_type)
        self.fields['barangay'].choices = self._choices(
            (
                (project['address'].get('barangay') or '')
                for project in self.projects
            ),
            'All barangays',
        )
        categories = {
            project['category'].get('code'): project['category'].get('name')
            for project in self.projects
            if project['category'].get('code')
        }
        self.fields['category'].choices = [
            ('', 'All categories'),
            *sorted(categories.items(), key=lambda item: item[1].casefold()),
        ]
        self.fields['date_from'].label = f'{self.date_field_label} from'
        self.fields['date_to'].label = f'{self.date_field_label} to'

    @staticmethod
    def _choices(values, empty_label):
        unique = sorted(
            {value for value in values if value},
            key=str.casefold,
        )
        return [('', empty_label), *((value, value) for value in unique)]

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get('date_from')
        date_to = cleaned.get('date_to')
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError(
                'The start of the date range must be on or before the end.',
            )
        return cleaned


class InfrastructureSummaryReportFilterForm(BaseSummaryReportFilterForm):
    report_type = 'infrastructure'
    date_field_label = 'Planned start date'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        statuses = {
            project['award_status']: project['award_status_label']
            for project in self.projects
            if project['award_status']
        }
        self.fields['status'].choices = [
            ('', 'All statuses'),
            *sorted(statuses.items(), key=lambda item: item[1].casefold()),
        ]


class NonInfrastructureSummaryReportFilterForm(BaseSummaryReportFilterForm):
    report_type = 'non_infrastructure'
    date_field_label = 'Event or service date'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        statuses = {
            project['status']: project['status_label']
            for project in self.projects
            if project['status']
        }
        self.fields['status'].choices = [
            ('', 'All statuses'),
            *sorted(statuses.items(), key=lambda item: item[1].casefold()),
        ]


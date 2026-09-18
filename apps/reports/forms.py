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


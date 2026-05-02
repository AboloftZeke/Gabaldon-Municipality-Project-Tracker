from django import forms
from .models import NonInfrastructureProject


class NonInfrastructureProjectForm(forms.ModelForm):
    """Form for creating and editing non-infrastructure projects"""

    class Meta:
        model = NonInfrastructureProject
        fields = [
            'title', 'description', 'location', 'implementing_office', 'category',
            'service_description', 'beneficiaries_description', 'service_location_details', 'service_period', 'service_time',
            'budget_cost', 'results_achieved',
            'source_of_fund', 'planned_start_date', 'planned_end_date',
            'actual_start_date', 'revised_completion_date', 'overall_progress_percentage',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Project Title'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'placeholder': 'Project description and objectives', 'rows': 4}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'implementing_office': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Office/Agency'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'service_description': forms.Textarea(attrs={'class': 'form-textarea', 'placeholder': 'What service or program is being delivered?', 'rows': 3}),
            'beneficiaries_description': forms.Textarea(attrs={'class': 'form-textarea', 'placeholder': 'To whom is the service delivered? (e.g., students, farmers, PWD, elderly)', 'rows': 3}),
            'service_location_details': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Specific location/venue where service is delivered'}),
            'service_period': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'When? (e.g., weekly, monthly, semester, one-time event)'}),
            'service_time': forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
            'budget_cost': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Amount in Pesos', 'min': '0', 'step': '0.01'}),
            'results_achieved': forms.Textarea(attrs={'class': 'form-textarea', 'placeholder': 'What were the results/outcomes? (e.g., number of beneficiaries, skills gained, health improvements)', 'rows': 4}),
            'source_of_fund': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g., GAA, PRDP'}),
            'planned_start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'planned_end_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'actual_start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'revised_completion_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'overall_progress_percentage': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Percentage (0-100)', 'min': '0', 'max': '100', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field not in ['category']:
                self.fields[field].required = False


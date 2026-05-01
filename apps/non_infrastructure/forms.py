from django import forms
from .models import NonInfrastructureProject


class NonInfrastructureProjectForm(forms.ModelForm):
    """Form for creating and editing non-infrastructure projects"""

    class Meta:
        model = NonInfrastructureProject
        fields = [
            'title', 'description', 'location', 'implementing_office', 'category',
            'source_of_fund', 'planned_start_date', 'planned_end_date',
            'actual_start_date', 'revised_completion_date', 'overall_progress_percentage',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Project Title'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'placeholder': 'Project description and objectives', 'rows': 4}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'implementing_office': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Office/Agency'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
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


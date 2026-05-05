from django import forms
from .models import InfrastructureProject


class InfrastructureProjectForm(forms.ModelForm):
    """Form for creating and editing infrastructure projects"""

    class Meta:
        model = InfrastructureProject
        fields = [
            'title', 'location', 'implementing_office', 'category', 'contractor',
            'procurement_method', 'award_status', 'source_of_fund', 'abc_amount',
            'contract_price', 'planned_start_date', 'planned_end_date',
            'actual_start_date', 'cost_progress_percentage',
            'physical_progress_percentage',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Project Title'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'implementing_office': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Office/Agency'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'contractor': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Company Name'}),
            'procurement_method': forms.Select(attrs={'class': 'form-select'}),
            'award_status': forms.Select(attrs={'class': 'form-select'}),
            'source_of_fund': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g., 20% Development Fund'}),
            'abc_amount': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Amount'}),
            'contract_price': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Amount'}),
            'planned_start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'planned_end_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'actual_start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'cost_progress_percentage': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Percentage (0-100)', 'min': '0', 'max': '100', 'step': '0.01'}),
            'physical_progress_percentage': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Percentage (0-100)', 'min': '0', 'max': '100', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field not in ['category', 'procurement_method', 'award_status']:
                self.fields[field].required = False

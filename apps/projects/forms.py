from django import forms
from .models import Project


class ProjectForm(forms.ModelForm):
    """Form for creating and editing infrastructure projects"""

    class Meta:
        model = Project
        fields = ['title', 'description', 'status', 'location', 'budget', 'start_date', 'end_date', 'assigned_to']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Project title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Project description',
                'rows': 4
            }),
            'status': forms.Select(attrs={
                'class': 'form-control'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Project location'
            }),
            'budget': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Budget amount',
                'step': '0.01'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'assigned_to': forms.Select(attrs={
                'class': 'form-control'
            }),
        }

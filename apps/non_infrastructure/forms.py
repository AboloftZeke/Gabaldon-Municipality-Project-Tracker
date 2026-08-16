from django import forms

from apps.system.models import (
    Project,
    Non_Infrastructure_Project,
    Address,
    NonInfrastructureCategory,
)


class NonInfrastructureProjectForm(forms.Form):
    title = forms.CharField(required=True, max_length=255)
    description = forms.CharField(required=False, widget=forms.Textarea, max_length=2000)
    location = forms.CharField(required=False, max_length=100)
    implementing_office = forms.CharField(required=False, max_length=255)
    category = forms.ModelChoiceField(
            queryset=NonInfrastructureCategory.objects.all().order_by('type_name'),
            required=False,
            empty_label='Select Category'
        )
    service_description = forms.CharField(required=False, widget=forms.Textarea)
    beneficiaries_description = forms.CharField(required=False, widget=forms.Textarea)
    service_location_details = forms.CharField(required=False, max_length=255)
    service_period = forms.CharField(required=False, max_length=100)
    service_time = forms.TimeField(required=False)
    budget_cost = forms.DecimalField(required=False, max_digits=15, decimal_places=2)
    results_achieved = forms.CharField(required=False, widget=forms.Textarea)
    source_of_fund = forms.CharField(required=False, max_length=255)
    planned_start_date = forms.DateField(required=False)
    planned_end_date = forms.DateField(required=False)
    actual_start_date = forms.DateField(required=False)
    revised_completion_date = forms.DateField(required=False)
    latitude = forms.DecimalField(required=False, max_digits=10, decimal_places=7)
    longitude = forms.DecimalField(required=False, max_digits=10, decimal_places=7)
    overall_progress_percentage = forms.DecimalField(required=False, max_digits=5, decimal_places=2)

    def save(self, user=None, instance=None):
        data = self.cleaned_data

        if instance is None:
            proj = Project.objects.create(project_type='non_infrastructure', created_by=user, updated_by=user)
        else:
            proj = Project.objects.filter(project_id=instance.non_infra_id).first()
            if proj is None:
                proj = Project.objects.create(project_type='non_infrastructure', created_by=user, updated_by=user)

        non = Non_Infrastructure_Project.objects.filter(project=proj).first()
        if non is None:
            non = Non_Infrastructure_Project(project=proj)

        non.non_infra_name = data.get('title')
        non.description = data.get('description') or ''
        non.non_infra_category = data.get('category')

        loc = data.get('location')
        if loc:
            if non.address:
                non.address.address = loc
                non.address.municipality = "Gabaldon"
                non.address.province = "Nueva Ecija"
                non.address.save()
            else:
                addr = Address.objects.create(
                    barangay=loc,
                    municipality="Gabaldon",
                    province="Nueva Ecija"
                )
                non.address = addr

        non.event_date = data.get('planned_start_date')
        non.start_time = data.get('service_time')
        non.end_time = None
        non.save()

        return non


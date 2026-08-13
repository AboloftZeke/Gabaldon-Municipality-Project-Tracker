from django import forms

from apps.system.models import (
    Project,
    Infrastructure_Project,
    Address,
    Contractor,
    ImplementingOffice,
    InfrastructureCategory,
    FundSource,
    Financial,
)


class InfrastructureProjectForm(forms.Form):
    """Compatibility form that writes into the normalized Project + Infrastructure_Project tables.

    This avoids touching the legacy tables and preserves the same user-facing fields.
    """

    title = forms.CharField(required=True, max_length=255)
    description = forms.CharField(required=False, widget=forms.Textarea, max_length=2000)
    location = forms.CharField(required=False, max_length=100)
    implementing_office = forms.CharField(required=False, max_length=255)
    category = forms.CharField(required=False, max_length=50)
    contractor = forms.CharField(required=False, max_length=255)
    procurement_method = forms.CharField(required=False, max_length=50)
    award_status = forms.CharField(required=False, max_length=50)
    source_of_fund = forms.CharField(required=False, max_length=255)
    abc_amount = forms.DecimalField(required=False, max_digits=15, decimal_places=2)
    contract_price = forms.DecimalField(required=False, max_digits=15, decimal_places=2)
    planned_start_date = forms.DateField(required=False)
    planned_end_date = forms.DateField(required=False)
    actual_start_date = forms.DateField(required=False)
    latitude = forms.DecimalField(required=False, max_digits=10, decimal_places=7)
    longitude = forms.DecimalField(required=False, max_digits=10, decimal_places=7)
    cost_progress_percentage = forms.DecimalField(required=False, max_digits=5, decimal_places=2)
    physical_progress_percentage = forms.DecimalField(required=False, max_digits=5, decimal_places=2)

    def save(self, user=None, instance=None):
        """Create or update normalized Project + Infrastructure_Project records.

        Returns the created/updated Infrastructure_Project instance.
        """
        data = self.cleaned_data

        # Create or update base Project
        if instance is None:
            proj = Project.objects.create(
                project_type='infrastructure',
                created_by_user=user,
                updated_by_user=user,
            )
        else:
            # instance is the compatibility object with id mapping to infrastructure_id
            proj = Project.objects.filter(project_id=instance.id).first()
            if proj is None:
                proj = Project.objects.create(project_type='infrastructure', created_by_user=user, updated_by_user=user)

        # Prepare or update Infrastructure_Project
        infra = Infrastructure_Project.objects.filter(project=proj).first()
        if infra is None:
            infra = Infrastructure_Project(project=proj)

        infra.infrastructure_title = data.get('title')
        infra.infrastructure_description = data.get('description') or ''

        # Category -> normalized lookup by code, fallback to create
        cat_code = data.get('category')
        if cat_code:
            cat = InfrastructureCategory.objects.filter(category_code=cat_code).first()
            if not cat:
                cat = InfrastructureCategory.objects.create(category_code=cat_code, category_name=cat_code)
            infra.category = cat

        # Address: keep minimal - store barangay from location
        loc = data.get('location')
        if loc:
            addr = Address.objects.create(barangay=loc, municipality='Gabaldon', province='Nueva Ecija')
            infra.address = addr

        # Contractor
        contractor_name = data.get('contractor')
        if contractor_name:
            contractor_obj, _ = Contractor.objects.get_or_create(contractor_name=str(contractor_name).strip(), defaults={'is_active': True})
            infra.contractor_id = contractor_obj.contractor_id

        # Implementing office
        office_name = data.get('implementing_office')
        if office_name:
            office_obj, _ = ImplementingOffice.objects.get_or_create(office_name=str(office_name).strip(), defaults={'is_active': True})
            infra.implementing_office_id = office_obj.office_id

        infra.procurement_method = data.get('procurement_method')
        infra.award_status = data.get('award_status')
        infra.planned_start_date = data.get('planned_start_date')
        infra.planned_end_date = data.get('planned_end_date')
        infra.cost_progress_percentage = data.get('cost_progress_percentage')
        infra.physical_progress_percentage = data.get('physical_progress_percentage')

        infra.save()

        # Financials
        abc = data.get('abc_amount')
        bid = data.get('contract_price')
        if abc or bid:
            Financial.objects.create(infrastructure=infra, approved_budget=abc, bid_amount=bid)

        return infra

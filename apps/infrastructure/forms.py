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
    Infrastructure_Schedule,
    Project_Inspection,
    Project_Image,
)
from django.core.files.storage import default_storage
from django.conf import settings
import os
from apps.infrastructure.models import InfrastructureProject as LocalInfrastructureProject


class InfrastructureProjectForm(forms.Form):
    """Compatibility form that writes into the normalized Project + Infrastructure_Project tables.

    This avoids touching the legacy tables and preserves the same user-facing fields.
    """

    title = forms.CharField(required=True, max_length=255)
    description = forms.CharField(required=False, widget=forms.Textarea, max_length=2000)
    # Street is free text; barangay is chosen from predefined LOCATION_CHOICES
    street = forms.CharField(required=False, max_length=500)
    barangay = forms.ChoiceField(required=False, choices=[('', '---')])
    latitude = forms.DecimalField(required=False, max_digits=10, decimal_places=7)
    longitude = forms.DecimalField(required=False, max_digits=10, decimal_places=7)
    # Municipality and province are fixed (Gabaldon, Nueva Ecija) and submitted via hidden inputs
    municipality = forms.CharField(required=False, widget=forms.HiddenInput())
    province = forms.CharField(required=False, widget=forms.HiddenInput())
    implementing_office = forms.CharField(required=False, max_length=255)
    category = forms.CharField(required=False, max_length=50)
    contractor = forms.CharField(required=False, max_length=255)
    procurement_method = forms.CharField(required=False, max_length=50)
    award_status = forms.CharField(required=False, max_length=50)
    source_of_fund = forms.CharField(required=False, max_length=255)
    abc_amount = forms.DecimalField(required=False, max_digits=15, decimal_places=2)
    contract_price = forms.DecimalField(required=False, max_digits=15, decimal_places=2)
    planned_start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    planned_end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    actual_start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    actual_completion_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    cost_progress_percentage = forms.DecimalField(required=False, max_digits=5, decimal_places=2)
    physical_progress_percentage = forms.DecimalField(required=False, max_digits=5, decimal_places=2)
    posting_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    pre_bid_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    bidding_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    notice_award_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    notice_to_proceed_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    duration_days = forms.IntegerField(required=False)

    fund_source = forms.CharField(required=False, max_length=255)
    actual_expenditure = forms.DecimalField(required=False, max_digits=15, decimal_places=2)

    # Single inspection/image support for create form; UI can submit multiple entries separately
    inspection_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    inspection_completion_percentage = forms.DecimalField(required=False, max_digits=5, decimal_places=2)
    inspection_findings = forms.CharField(required=False, max_length=2000)
    inspection_remarks = forms.CharField(required=False, max_length=2000)

    # Upload an image file; we store the saved file URL on `Project_Image.image_url`.
    image_file = forms.ImageField(required=False)

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

        # Address: keep minimal - store barangay from barangay field
        street = data.get('street')
        barangay = data.get('barangay')
        municipality = data.get('municipality') or 'Gabaldon'
        province = data.get('province') or 'Nueva Ecija'
        if street or barangay or municipality or province:
            if infra.address:
                addr = infra.address
                addr.street = street or addr.street
                addr.barangay = barangay or addr.barangay
                addr.municipality = municipality or addr.municipality
                addr.province = province or addr.province
                addr.save()
            else:
                addr = Address.objects.create(street=street, barangay=barangay, municipality=municipality, province=province)
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

        # Schedule
        posting = data.get('posting_date')
        pre_bid = data.get('pre_bid_date')
        bidding = data.get('bidding_date')
        notice_award = data.get('notice_award_date')
        notice_proceed = data.get('notice_to_proceed_date')
        duration = data.get('duration_days')
        actual_start = data.get('actual_start_date')
        actual_completion = data.get('actual_completion_date')
        if posting or pre_bid or bidding or notice_award or notice_proceed or duration or actual_start or actual_completion:
            sched = Infrastructure_Schedule.objects.filter(infrastructure=infra).first()
            if not sched:
                sched = Infrastructure_Schedule(infrastructure=infra)
            sched.posting_date = posting or sched.posting_date
            sched.pre_bid_date = pre_bid or sched.pre_bid_date
            sched.bidding_date = bidding or sched.bidding_date
            sched.notice_award_date = notice_award or sched.notice_award_date
            # normalized field name is `notice_proceed_date`
            sched.notice_proceed_date = notice_proceed or getattr(sched, 'notice_proceed_date', None)
            sched.duration_days = duration or sched.duration_days
            sched.actual_start_date = actual_start or sched.actual_start_date
            sched.actual_completion_date = actual_completion or sched.actual_completion_date
            sched.save()

        # Financials
        # Financials
        abc = data.get('abc_amount')
        bid = data.get('contract_price')
        fund_source_name = data.get('fund_source')
        actual_exp = data.get('actual_expenditure')
        if abc or bid or actual_exp or fund_source_name:
            fs = None
            if fund_source_name:
                fs = FundSource.objects.filter(fund_source_name=fund_source_name).first()
                if not fs:
                    fs = FundSource.objects.create(fund_source_name=fund_source_name, fund_source_code=fund_source_name)
            Financial.objects.create(infrastructure=infra, approved_budget=abc, bid_amount=bid, fund_source=fs, actual_expenditure=actual_exp or 0)

        # Inspections
        insp_date = data.get('inspection_date')
        insp_pct = data.get('inspection_completion_percentage')
        insp_findings = data.get('inspection_findings')
        insp_remarks = data.get('inspection_remarks')
        if insp_date or insp_pct is not None or insp_findings or insp_remarks:
            Project_Inspection.objects.create(
                project=proj,
                inspection_date=insp_date or (insp_date if insp_date else None) or None,
                inspected_by_user=user,
                completion_percentage=insp_pct or 0,
                findings=insp_findings or '',
                remarks=insp_remarks or ''
            )

        # Project image
        img_file = data.get('image_file')
        if img_file:
            # Save under MEDIA_ROOT/projects/<project_id>/<filename>
            folder = os.path.join('projects', str(proj.project_id))
            filename = default_storage.save(os.path.join(folder, img_file.name), img_file)
            file_url = default_storage.url(filename)
            Project_Image.objects.create(
                project=proj,
                image_url=file_url,
            )

        return infra

    def __init__(self, *args, **kwargs):
        # Accept an optional `instance` kwarg for compatibility with
        # Django generic views (UpdateView passes `instance=`). Pop it
        # and use it to populate initial values for the form fields.
        instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self._instance = instance
        # Populate barangay choices from model LOCATION_CHOICES and set fixed municipality/province
        try:
            barangay_choices = [('', '---')] + list(LocalInfrastructureProject.LOCATION_CHOICES)
            self.fields['barangay'].choices = barangay_choices
            # Defaults for this app
            if not self.initial.get('municipality'):
                self.initial['municipality'] = 'Gabaldon'
            if not self.initial.get('province'):
                self.initial['province'] = 'Nueva Ecija'
        except Exception:
            # If model import/DB not available, leave defaults
            if not self.initial.get('municipality'):
                self.initial['municipality'] = 'Gabaldon'
            if not self.initial.get('province'):
                self.initial['province'] = 'Nueva Ecija'

        if instance is not None:
            # `instance` is the compatibility model `InfrastructureProject`.
            # Attempt to map legacy fields to form initial values and also
            # resolve related normalized records where necessary.
            try:
                infra = Infrastructure_Project.objects.filter(infrastructure_id=instance.id).select_related('project').first()
            except Exception:
                infra = None

            if infra:
                proj = infra.project if hasattr(infra, 'project') else None
                fin = infra.financial_records.first()
                self.initial.setdefault('title', getattr(instance, 'title', ''))
                self.initial.setdefault('description', getattr(instance, 'description', ''))
                self.initial.setdefault('implementing_office', getattr(instance, 'implementing_office', '') or '')
                self.initial.setdefault('procurement_method', getattr(instance, 'procurement_method', '') or '')
                self.initial.setdefault('award_status', getattr(instance, 'award_status', '') or '')
                self.initial.setdefault('planned_start_date', getattr(instance, 'planned_start_date', None))
                self.initial.setdefault('planned_end_date', getattr(instance, 'planned_end_date', None))
                self.initial.setdefault('cost_progress_percentage', getattr(instance, 'cost_progress_percentage', None))
                self.initial.setdefault('physical_progress_percentage', getattr(instance, 'physical_progress_percentage', None))
                if fin:
                    self.initial.setdefault('abc_amount', fin.approved_budget)
                    self.initial.setdefault('contract_price', fin.bid_amount)
                # Address
                if infra.address:
                    self.initial.setdefault('street', infra.address.street)
                    self.initial.setdefault('barangay', infra.address.barangay)
                    self.initial.setdefault('municipality', infra.address.municipality)
                    self.initial.setdefault('province', infra.address.province)
                # Schedule
                sched = infra.schedules.first()
                if sched:
                    self.initial.setdefault('posting_date', sched.posting_date)
                    self.initial.setdefault('pre_bid_date', sched.pre_bid_date)
                    self.initial.setdefault('bidding_date', sched.bidding_date)
                    self.initial.setdefault('notice_award_date', sched.notice_award_date)
                    self.initial.setdefault('notice_to_proceed_date', getattr(sched, 'notice_proceed_date', None))
                    self.initial.setdefault('duration_days', sched.duration_days)
                    self.initial.setdefault('actual_start_date', sched.actual_start_date)
                    self.initial.setdefault('actual_completion_date', sched.actual_completion_date)
                # Financial
                if fin:
                    self.initial.setdefault('fund_source', fin.fund_source and fin.fund_source.fund_source_name)
                    self.initial.setdefault('actual_expenditure', fin.actual_expenditure)
                # Inspections: populate most recent
                insp = proj.inspections.first() if proj and hasattr(proj, 'inspections') else None
                if insp:
                    self.initial.setdefault('inspection_date', insp.inspection_date)
                    self.initial.setdefault('inspection_completion_percentage', insp.completion_percentage)
                    self.initial.setdefault('inspection_findings', insp.findings)
                    self.initial.setdefault('inspection_remarks', insp.remarks)
                # Images: we cannot pre-populate file inputs. Leave upload fields empty.

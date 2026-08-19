from unicodedata import category
from django.db import IntegrityError

from django import forms
from django.core.files.storage import default_storage
import os

from apps.infrastructure.models import InfrastructureProject as LocalInfrastructureProject
from apps.system.models import (
    Address,
    Contractor,
    Financial,
    FundSource,
    ImplementingOffice,
    InfrastructureCategory,
    Infrastructure_Project,
    Infrastructure_Schedule,
    Project,
    Project_Image,
    Project_Inspection,
)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        if not isinstance(data, (list, tuple)):
            data = [data]

        cleaned = []
        for item in data:
            if item in self.empty_values:
                continue
            cleaned.append(super().clean(item, initial))
        return cleaned


class InfrastructureProjectForm(forms.Form):
    """Compatibility form writing to the normalized project tables."""

    title = forms.CharField(required=True, max_length=255)
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4}), max_length=2000)
    street = forms.CharField(required=False, max_length=500)
    barangay = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Select Barangay'),
            ('Bagting', 'Bagting'),
            ('Bantug', 'Bantug'),
            ('Bitulok', 'Bitulok'),
            ('Bugnan', 'Bugnan'),
            ('Calabasa', 'Calabasa'),
            ('Camachile', 'Camachile'),
            ('Cuyapa', 'Cuyapa'),
            ('Gabaldon', 'Gabaldon'),
            ('Labney', 'Labney'),
            ('Ligaya', 'Ligaya'),
            ('Malinao', 'Malinao'),
            ('Pantoc', 'Pantoc'),
            ('Sawmill', 'Sawmill'),
            ('South Poblacion', 'South Poblacion'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
    )
    latitude = forms.DecimalField(required=False, max_digits=10, decimal_places=7, min_value=-90, max_value=90)
    longitude = forms.DecimalField(required=False, max_digits=10, decimal_places=7, min_value=-180, max_value=180)
    municipality = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={'readonly': 'readonly'}),
        disabled=True,
    )
    province = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={'readonly': 'readonly'}),
        disabled=True,
    )

    category = forms.ModelChoiceField(
        required=True,
        queryset=InfrastructureCategory.objects.none(),
        empty_label='Select Category',
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_category',
        }),
    )

    other_category = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'id_other_category',
            'placeholder': 'Enter category'
        })
    )
    implementing_office = forms.ModelChoiceField(
        required=False,
        queryset=ImplementingOffice.objects.none(),
        empty_label='Select Implementing Office',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    contractor = forms.ModelChoiceField(
        required=False,
        queryset=Contractor.objects.none(),
        empty_label='Select Contractor',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    procurement_method = forms.ChoiceField(
        required=True,
        choices=[('', 'Select Procurement Method')] + list(Infrastructure_Project.PROCUREMENT_METHOD_CHOICES),
        widget=forms.Select,
    )
    award_status = forms.ChoiceField(
        required=True,
        choices=[('', 'Select Award Status')] + list(Infrastructure_Project.AWARD_STATUS_CHOICES),
        widget=forms.Select,
    )
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
    fund_source = forms.ModelChoiceField(
        required=False,
        queryset=FundSource.objects.none(),
        empty_label='Select Fund Source',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    actual_expenditure = forms.DecimalField(required=False, max_digits=15, decimal_places=2)

    inspection_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    inspection_completion_percentage = forms.DecimalField(required=False, max_digits=5, decimal_places=2)
    inspection_findings = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))
    inspection_remarks = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))

    project_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={'accept': 'image/*'}),
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self._instance = instance

        self.fields['category'].queryset = InfrastructureCategory.objects.filter(
            is_active=True
        ).order_by('category_name')
        self.fields['implementing_office'].queryset = ImplementingOffice.objects.filter(
            is_active=True
        ).order_by('office_name')
        self.fields['contractor'].queryset = Contractor.objects.filter(
            is_active=True
        ).order_by('contractor_name')
        self.fields['fund_source'].queryset = FundSource.objects.filter(
            is_active=True
        ).order_by('fund_source_name')
        self.fields['municipality'].initial = 'Gabaldon'
        self.fields['province'].initial = 'Nueva Ecija'
        self.fields['municipality'].widget.attrs['readonly'] = 'readonly'
        self.fields['province'].widget.attrs['readonly'] = 'readonly'

        if instance is not None:
            self._populate_from_instance(instance)

    def _resolve_infrastructure_instance(self, instance):
        if instance is None:
            return None

        if isinstance(instance, Infrastructure_Project):
            return instance

        infrastructure_id = getattr(instance, 'infrastructure_id', None)
        if infrastructure_id is not None:
            return Infrastructure_Project.objects.filter(infrastructure_id=infrastructure_id).select_related(
                'project', 'address', 'category'
            ).first()

        project_id = getattr(instance, 'project_id', getattr(instance, 'id', None))
        if project_id is not None:
            infra = Infrastructure_Project.objects.filter(project_id=project_id).select_related(
                'project', 'address', 'category'
            ).first()
            if infra is not None:
                return infra

        project = getattr(instance, 'project', None)
        if project is not None:
            return Infrastructure_Project.objects.filter(project=project).select_related(
                'project', 'address', 'category'
            ).first()

        return None

    def _populate_from_instance(self, instance):
        infra = self._resolve_infrastructure_instance(instance)
        if infra is None:
            return

        self.initial.setdefault('title', infra.infrastructure_title)
        self.initial.setdefault('description', infra.infrastructure_description)
        self.initial.setdefault('category', infra.category_id)

        self.initial.setdefault('contractor', infra.contractor_id)
        self.initial.setdefault(
            'implementing_office',
            infra.implementing_office_id,
        )

        self.initial.setdefault('procurement_method', infra.procurement_method)
        self.initial.setdefault('award_status', infra.award_status)
        self.initial.setdefault('cost_progress_percentage', infra.cost_progress_percentage)
        self.initial.setdefault('physical_progress_percentage', infra.physical_progress_percentage)

        if infra.address:
            self.initial.setdefault('street', infra.address.street)
            self.initial.setdefault('barangay', infra.address.barangay)
            self.initial.setdefault('latitude', infra.address.latitude)
            self.initial.setdefault('longitude', infra.address.longitude)
            self.initial.setdefault('municipality', infra.address.municipality or 'Gabaldon')
            self.initial.setdefault('province', infra.address.province or 'Nueva Ecija')

        fin = infra.financial_records.first()
        if fin:
            self.initial.setdefault('abc_amount', fin.approved_budget)
            self.initial.setdefault('contract_price', fin.bid_amount)
            self.initial.setdefault('fund_source', fin.fund_source_id)
            self.initial.setdefault('actual_expenditure', fin.actual_expenditure)

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

        if infra.project:
            latest_inspection = infra.project.inspections.order_by('-inspection_date', '-created_at').first()
            if latest_inspection:
                self.initial.setdefault('inspection_date', latest_inspection.inspection_date)
                self.initial.setdefault('inspection_completion_percentage', latest_inspection.completion_percentage)
                self.initial.setdefault('inspection_findings', latest_inspection.findings)
                self.initial.setdefault('inspection_remarks', latest_inspection.remarks)

    def clean(self):
        cleaned_data = super().clean()
        category_obj = cleaned_data.get('category')
        other_category = (cleaned_data.get('other_category') or '').strip()

        if (
            category_obj is not None
            and category_obj.category_code.lower() == 'other'
            and not other_category
        ):
            self.add_error(
                'other_category',
                'Enter a category name when Other is selected.',
            )

        return cleaned_data

    def clean_municipality(self):
        return 'Gabaldon'

    def clean_province(self):
        return 'Nueva Ecija'

    def _save_images(self, project):
        uploaded_files = []
        if hasattr(self, 'files') and self.files:
            raw_files = self.files.getlist('project_images') if hasattr(self.files, 'getlist') else self.files.get('project_images', [])
            if isinstance(raw_files, (list, tuple)):
                uploaded_files = raw_files
            else:
                uploaded_files = [raw_files]

        if not uploaded_files:
            return

        project.images.all().delete()
        for upload in uploaded_files:
            if not upload or not getattr(upload, 'name', None):
                continue
            folder = os.path.join('projects', str(project.project_id))
            filename = default_storage.save(os.path.join(folder, upload.name), upload)
            file_url = default_storage.url(filename)
            Project_Image.objects.create(project=project, image_url=file_url)
    def _get_or_create_implementing_office(self, name):
        name = (name or '').strip()

        if not name:
            return None

        office = ImplementingOffice.objects.filter(
            office_name__iexact=name
        ).first()

        if office:
            return office

        return ImplementingOffice.objects.create(
            office_name=name
        )


    def _get_or_create_contractor(self, name):
        name = (name or '').strip()

        if not name:
            return None

        contractor = Contractor.objects.filter(
            contractor_name__iexact=name
        ).first()

        if contractor:
            return contractor

        return Contractor.objects.create(
            contractor_name=name
        )


    def _get_or_create_fund_source(self, name):
        name = (name or '').strip()

        if not name:
            return None

        fund_source = FundSource.objects.filter(
            fund_source_name__iexact=name
        ).first()

        if fund_source:
            return fund_source

    # Generate a code for a new fund source
        base_code = name.upper().replace(' ', '_')
        code = base_code

        counter = 1

        while FundSource.objects.filter(
            fund_source_code=code
        ).exists():
            counter += 1
            code = f'{base_code}_{counter}'

        return FundSource.objects.create(
            fund_source_name=name,
            fund_source_code=code
        )

    def save(self, user=None, instance=None):
        data = self.cleaned_data

        if instance is None:
            proj = Project.objects.create(
                project_type='infrastructure',
                created_by_user=user,
                updated_by_user=user,
            )
            infra = Infrastructure_Project.objects.filter(project=proj).first()
            if infra is None:
                infra = Infrastructure_Project(project=proj)
        else:
            resolved = self._resolve_infrastructure_instance(instance)
            if resolved is not None:
                proj = resolved.project
                infra = resolved
            else:
                project_id = getattr(instance, 'project_id', getattr(instance, 'id', None))
                proj = Project.objects.filter(project_id=project_id).first()
                if proj is None:
                    proj = Project.objects.create(
                        project_type='infrastructure',
                        created_by_user=user,
                        updated_by_user=user,
                    )
                infra = Infrastructure_Project.objects.filter(project=proj).first()
                if infra is None:
                    infra = Infrastructure_Project(project=proj)

        infra.infrastructure_title = data.get('title') or infra.infrastructure_title
        infra.infrastructure_description = data.get('description') or ''

        category_obj = data.get('category')

        if (
            category_obj is not None
            and category_obj.category_code.lower() == 'other'
        ):
            category_name = (data.get('other_category') or '').strip()
            category_obj = InfrastructureCategory.objects.filter(
                category_name__iexact=category_name
            ).first()

            if category_obj is None:
                category_code = (
                    category_name.lower()
                    .strip()
                    .replace(' ', '_')
                    .replace('-', '_')
                    .replace('/', '_')
                )
                base_code = category_code
                counter = 1

                while InfrastructureCategory.objects.filter(
                    category_code=category_code
                ).exists():
                    counter += 1
                    category_code = f'{base_code}_{counter}'

                try:
                    category_obj = InfrastructureCategory.objects.create(
                        category_name=category_name,
                        category_code=category_code,
                    )
                except IntegrityError:
                    category_obj = InfrastructureCategory.objects.filter(
                        category_name__iexact=category_name
                    ).first()
                    if category_obj is None:
                        raise

        infra.category = category_obj

        street = data.get('street') or ''
        barangay = data.get('barangay') or ''
        municipality = 'Gabaldon'
        province = 'Nueva Ecija'

        if infra.address:
            addr = infra.address
        else:
            addr = Address.objects.create(
                street=street,
                barangay=barangay,
                municipality=municipality,
                province=province,
            )
            infra.address = addr

        addr.street = street
        addr.barangay = barangay
        addr.latitude = data.get('latitude')
        addr.longitude = data.get('longitude')
        addr.municipality = municipality
        addr.province = province
        addr.save()
        infra.address = addr

        infra.contractor = data.get('contractor')
        infra.implementing_office = data.get('implementing_office')
        infra.procurement_method = data.get('procurement_method')
        infra.award_status = data.get('award_status')
        infra.planned_start_date = data.get('planned_start_date')
        infra.planned_end_date = data.get('planned_end_date')
        infra.cost_progress_percentage = data.get('cost_progress_percentage')
        infra.physical_progress_percentage = data.get('physical_progress_percentage')
        infra.save()

        posting = data.get('posting_date')
        pre_bid = data.get('pre_bid_date')
        bidding = data.get('bidding_date')
        notice_award = data.get('notice_award_date')
        notice_proceed = data.get('notice_to_proceed_date')
        duration = data.get('duration_days')
        actual_start = data.get('actual_start_date')
        actual_completion = data.get('actual_completion_date')
        existing_sched = Infrastructure_Schedule.objects.filter(
            infrastructure=infra
        ).first()
        if (
            posting
            or pre_bid
            or bidding
            or notice_award
            or notice_proceed
            or duration is not None
            or actual_start
            or actual_completion
            or existing_sched is not None
        ):
            sched = existing_sched or Infrastructure_Schedule(
                infrastructure=infra
            )
            sched.posting_date = posting
            sched.pre_bid_date = pre_bid
            sched.bidding_date = bidding
            sched.notice_award_date = notice_award
            sched.notice_proceed_date = notice_proceed
            sched.duration_days = duration
            sched.actual_start_date = actual_start
            sched.actual_completion_date = actual_completion
            sched.save()

        abc = data.get('abc_amount')
        bid = data.get('contract_price')
        fund_source = data.get('fund_source')
        actual_exp = data.get('actual_expenditure')
        existing_fin = infra.financial_records.order_by('-financial_id').first()

        if (
            abc is not None
            or bid is not None
            or fund_source is not None
            or actual_exp is not None
            or existing_fin is not None
        ):
            fin = existing_fin or Financial(infrastructure=infra)
            fin.approved_budget = abc
            fin.bid_amount = bid
            fin.fund_source = fund_source
            fin.actual_expenditure = actual_exp if actual_exp is not None else 0
            fin.save()

        insp_date = data.get('inspection_date')
        insp_pct = data.get('inspection_completion_percentage')
        insp_findings = data.get('inspection_findings')
        insp_remarks = data.get('inspection_remarks')
        if insp_date or insp_pct is not None or insp_findings or insp_remarks:
            Project_Inspection.objects.create(
                project=proj,
                inspection_date=insp_date,
                inspected_by_user=user,
                completion_percentage=insp_pct if insp_pct is not None else 0,
                findings=insp_findings or '',
                remarks=insp_remarks or '',
            )

        self._save_images(proj)
        return infra

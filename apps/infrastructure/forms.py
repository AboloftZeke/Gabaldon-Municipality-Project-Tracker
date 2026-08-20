from django.db import IntegrityError

from django import forms
from django.core.files.storage import default_storage
import os

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
    implementing_office = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter implementing office',
        }),
    )
    contractor = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter contractor or company name',
        }),
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
    abc_amount = forms.DecimalField(
        required=False,
        max_digits=15,
        decimal_places=2,
        min_value=0,
    )
    contract_price = forms.DecimalField(
        required=False,
        max_digits=15,
        decimal_places=2,
        min_value=0,
    )
    planned_start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    planned_end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    actual_start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    actual_completion_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    cost_progress_percentage = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
    )
    physical_progress_percentage = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
    )
    posting_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    pre_bid_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    bidding_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    notice_award_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    notice_to_proceed_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    duration_days = forms.IntegerField(required=False, min_value=1)
    fund_source = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter fund source',
        }),
    )
    actual_expenditure = forms.DecimalField(
        required=False,
        max_digits=15,
        decimal_places=2,
        min_value=0,
    )

    inspection_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    inspection_completion_percentage = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
    )
    inspection_findings = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))
    inspection_remarks = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))

    project_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={'accept': 'image/*'}),
    )
    images_to_delete = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    cover_image_selection = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self._instance = instance
        self.existing_images = []

        self.fields['category'].queryset = InfrastructureCategory.objects.filter(
            is_active=True
        ).order_by('category_name')
        self.fields['municipality'].initial = 'Gabaldon'
        self.fields['province'].initial = 'Nueva Ecija'
        self.fields['municipality'].widget.attrs['readonly'] = 'readonly'
        self.fields['province'].widget.attrs['readonly'] = 'readonly'

        if instance is not None:
            self._populate_from_instance(instance)
            infra = self._resolve_infrastructure_instance(instance)
            if infra is not None and infra.project:
                self.existing_images = list(
                    infra.project.images.order_by('-is_cover', '-created_at')
                )
                existing_cover = next(
                    (
                        image
                        for image in self.existing_images
                        if image.is_cover
                    ),
                    self.existing_images[0] if self.existing_images else None,
                )
                if existing_cover:
                    self.fields['cover_image_selection'].initial = (
                        f'existing:{existing_cover.pk}'
                    )

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

        self.initial.setdefault(
            'contractor',
            infra.contractor.contractor_name if infra.contractor else '',
        )
        self.initial.setdefault(
            'implementing_office',
            infra.implementing_office.office_name if infra.implementing_office else '',
        )

        self.initial.setdefault('procurement_method', infra.procurement_method)
        self.initial.setdefault('award_status', infra.award_status)
        self.initial.setdefault('planned_start_date', infra.planned_start_date)
        self.initial.setdefault('planned_end_date', infra.planned_end_date)
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
            self.initial.setdefault(
                'fund_source',
                fin.fund_source.fund_source_name if fin.fund_source else '',
            )
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
            latest_inspection = infra.project.inspections.order_by(
                '-inspection_date',
                '-created_at',
            ).first()
            if latest_inspection:
                self.initial.setdefault(
                    'inspection_date',
                    latest_inspection.inspection_date,
                )
                self.initial.setdefault(
                    'inspection_completion_percentage',
                    latest_inspection.completion_percentage,
                )
                self.initial.setdefault(
                    'inspection_findings',
                    latest_inspection.findings,
                )
                self.initial.setdefault(
                    'inspection_remarks',
                    latest_inspection.remarks,
                )

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

        inspection_date = cleaned_data.get('inspection_date')
        inspection_details = (
            cleaned_data.get('inspection_completion_percentage') is not None
            or bool((cleaned_data.get('inspection_findings') or '').strip())
            or bool((cleaned_data.get('inspection_remarks') or '').strip())
        )
        if inspection_details and not inspection_date:
            self.add_error(
                'inspection_date',
                'Enter an inspection date when recording inspection details.',
            )

        planned_start = cleaned_data.get('planned_start_date')
        planned_end = cleaned_data.get('planned_end_date')
        if planned_start and planned_end and planned_end < planned_start:
            self.add_error(
                'planned_end_date',
                'Planned end date cannot be earlier than the planned start date.',
            )

        actual_start = cleaned_data.get('actual_start_date')
        actual_completion = cleaned_data.get('actual_completion_date')
        if (
            actual_start
            and actual_completion
            and actual_completion < actual_start
        ):
            self.add_error(
                'actual_completion_date',
                'Actual completion date cannot be earlier than the actual start date.',
            )

        procurement_dates = [
            ('posting_date', 'Posting date'),
            ('pre_bid_date', 'Pre-bid date'),
            ('bidding_date', 'Bidding date'),
            ('notice_award_date', 'Notice of award date'),
            ('notice_to_proceed_date', 'Notice to proceed date'),
        ]
        populated_dates = [
            (field_name, label, cleaned_data.get(field_name))
            for field_name, label in procurement_dates
            if cleaned_data.get(field_name)
        ]
        for previous, current in zip(
            populated_dates,
            populated_dates[1:],
        ):
            _, previous_label, previous_date = previous
            current_field, current_label, current_date = current
            if current_date < previous_date:
                self.add_error(
                    current_field,
                    f'{current_label} cannot be earlier than {previous_label.lower()}.',
                )

        return cleaned_data

    def clean_municipality(self):
        return 'Gabaldon'

    def clean_province(self):
        return 'Nueva Ecija'

    def _save_images(self, project):
        cover_selection = self.cleaned_data.get(
            'cover_image_selection',
            '',
        )
        images_to_delete = self.cleaned_data.get('images_to_delete', '')

        image_ids = [
            int(image_id.strip())
            for image_id in images_to_delete.split(',')
            if image_id.strip().isdigit()
        ]
        if image_ids:
            project.images.filter(pk__in=image_ids).delete()

        raw_files = []
        if hasattr(self, 'files') and self.files:
            raw_files = (
                self.files.getlist('project_images')
                if hasattr(self.files, 'getlist')
                else self.files.get('project_images', [])
            )
        uploaded_files = (
            raw_files
            if isinstance(raw_files, (list, tuple))
            else [raw_files]
        )

        saved_images = []
        for upload in uploaded_files:
            if not upload or not getattr(upload, 'name', None):
                continue
            folder = os.path.join('projects', str(project.project_id))
            filename = default_storage.save(
                os.path.join(folder, upload.name),
                upload,
            )
            saved_images.append(
                Project_Image.objects.create(
                    project=project,
                    image_url=default_storage.url(filename),
                )
            )

        selected_cover = None
        if cover_selection.startswith('existing:'):
            image_id = cover_selection.removeprefix('existing:')
            if image_id.isdigit():
                selected_cover = project.images.filter(
                    pk=int(image_id)
                ).first()
        elif cover_selection.startswith('new:'):
            image_index = cover_selection.removeprefix('new:')
            if image_index.isdigit():
                index = int(image_index)
                if 0 <= index < len(saved_images):
                    selected_cover = saved_images[index]

        if selected_cover is None:
            selected_cover = (
                project.images.filter(is_cover=True).first()
                or project.images.order_by('-created_at').first()
            )

        project.images.update(is_cover=False)
        if selected_cover:
            project.images.filter(pk=selected_cover.pk).update(is_cover=True)

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

        contractor_name = (data.get('contractor') or '').strip()
        contractor_obj = None
        if contractor_name:
            contractor_obj = Contractor.objects.filter(
                contractor_name__iexact=contractor_name
            ).first()
            if contractor_obj is None:
                try:
                    contractor_obj = Contractor.objects.create(
                        contractor_name=contractor_name,
                    )
                except IntegrityError:
                    contractor_obj = Contractor.objects.filter(
                        contractor_name__iexact=contractor_name
                    ).first()
                    if contractor_obj is None:
                        raise

        implementing_office_name = (data.get('implementing_office') or '').strip()
        implementing_office_obj = None
        if implementing_office_name:
            implementing_office_obj = ImplementingOffice.objects.filter(
                office_name__iexact=implementing_office_name
            ).first()
            if implementing_office_obj is None:
                try:
                    implementing_office_obj = ImplementingOffice.objects.create(
                        office_name=implementing_office_name,
                    )
                except IntegrityError:
                    implementing_office_obj = ImplementingOffice.objects.filter(
                        office_name__iexact=implementing_office_name
                    ).first()
                    if implementing_office_obj is None:
                        raise

        infra.contractor = contractor_obj
        infra.implementing_office = implementing_office_obj
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
        fund_source_name = (data.get('fund_source') or '').strip()
        fund_source_obj = None
        if fund_source_name:
            fund_source_obj = FundSource.objects.filter(
                fund_source_name__iexact=fund_source_name
            ).first()
            if fund_source_obj is None:
                try:
                    fund_source_obj = FundSource.objects.create(
                        fund_source_name=fund_source_name,
                    )
                except IntegrityError:
                    fund_source_obj = FundSource.objects.filter(
                        fund_source_name__iexact=fund_source_name
                    ).first()
                    if fund_source_obj is None:
                        raise

        actual_exp = data.get('actual_expenditure')
        existing_fin = infra.financial_records.order_by('-financial_id').first()

        if (
            abc is not None
            or bid is not None
            or fund_source_obj is not None
            or actual_exp is not None
            or existing_fin is not None
        ):
            fin = existing_fin or Financial(infrastructure=infra)
            fin.approved_budget = abc
            fin.bid_amount = bid
            fin.fund_source = fund_source_obj
            fin.actual_expenditure = actual_exp if actual_exp is not None else 0
            fin.save()

        insp_date = data.get('inspection_date')
        insp_pct = data.get('inspection_completion_percentage')
        insp_findings = data.get('inspection_findings')
        insp_remarks = data.get('inspection_remarks')
        if insp_date or insp_pct is not None or insp_findings or insp_remarks:
            inspection = None
            if instance is not None:
                inspection = proj.inspections.order_by(
                    '-inspection_date',
                    '-created_at',
                ).first()

            if inspection is None:
                inspection = Project_Inspection(project=proj)

            inspection.inspection_date = insp_date
            inspection.inspected_by_user = user
            inspection.completion_percentage = (
                insp_pct if insp_pct is not None else 0
            )
            inspection.findings = insp_findings or ''
            inspection.remarks = insp_remarks or ''
            inspection.save()

        self._save_images(proj)
        return infra

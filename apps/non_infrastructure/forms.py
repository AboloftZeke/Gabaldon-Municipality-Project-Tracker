import os

from django import forms
from django.core.files.storage import default_storage
from django.db import transaction

from apps.system.choices import BARANGAY_CHOICES
from apps.system.models import (
    Address,
    NonInfrastructureCategory,
    NonInfrastructureEvidence,
    NonInfrastructureProgressUpdate,
    NonInfrastructureProject,
    Project,
    ProjectImage,
)
from apps.system.publication_images import retire_project_images


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


class NonInfrastructureProgressUpdateForm(forms.Form):
    """Save a staff proposal and its evidence without changing official status."""

    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    IMAGE_CONTENT_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    DOCUMENT_EXTENSIONS = {'.pdf'}
    DOCUMENT_CONTENT_TYPES = {'application/pdf'}
    MAX_EVIDENCE_SIZE = 10 * 1024 * 1024

    proposed_status = forms.ChoiceField(
        choices=NonInfrastructureProject.STATUS_CHOICES,
        label='Proposed Status',
    )
    remarks = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}))
    evidence_files = MultipleFileField(
        required=False,
        label='Supporting Evidence',
        widget=MultipleFileInput(attrs={'accept': '.jpg,.jpeg,.png,.gif,.webp,.pdf'}),
    )
    evidence_description = forms.CharField(
        required=False,
        max_length=2000,
        label='Evidence Description',
        widget=forms.Textarea(attrs={'rows': 2}),
    )

    def clean_evidence_files(self):
        uploads = self.cleaned_data['evidence_files']
        if not uploads:
            raise forms.ValidationError('Upload at least one supporting file.')
        for upload in uploads:
            extension = os.path.splitext(upload.name)[1].lower()
            content_type = (getattr(upload, 'content_type', '') or '').lower()
            if not (
                (extension in self.IMAGE_EXTENSIONS and content_type in self.IMAGE_CONTENT_TYPES)
                or (extension in self.DOCUMENT_EXTENSIONS and content_type in self.DOCUMENT_CONTENT_TYPES)
            ):
                raise forms.ValidationError('Only JPG, PNG, GIF, WebP, and PDF files are supported.')
            if upload.size > self.MAX_EVIDENCE_SIZE:
                raise forms.ValidationError('Each supporting file must be 10 MB or smaller.')
        return uploads

    def save(self, *, project, user):
        if not self.is_valid():
            raise ValueError('Cannot save an invalid progress update form.')

        stored_files = []
        try:
            with transaction.atomic():
                # Capture the official status at save time, even if another user
                # changed it after this form was opened.
                project = NonInfrastructureProject.objects.select_for_update().get(pk=project.pk)
                update = NonInfrastructureProgressUpdate.objects.create(
                    non_infrastructure=project,
                    previous_status=project.status,
                    proposed_status=self.cleaned_data['proposed_status'],
                    remarks=self.cleaned_data['remarks'],
                    submitted_by=user,
                    review_status=NonInfrastructureProgressUpdate.ReviewStatus.DRAFT,
                )
                for upload in self.cleaned_data['evidence_files']:
                    evidence = NonInfrastructureEvidence.objects.create(
                        progress_update=update,
                        evidence_file=upload,
                        description=self.cleaned_data['evidence_description'],
                        uploaded_by=user,
                    )
                    stored_files.append(evidence.evidence_file.name)
        except Exception:
            # Database rollback does not automatically remove saved media files.
            for name in stored_files:
                default_storage.delete(name)
            raise
        return update


NON_INFRA_CATEGORY_DEFAULTS = [
    ('social_services', 'Social Services'),
    ('community_development', 'Community Development'),
    ('livelihood', 'Livelihood Programs'),
    ('governance', 'Governance'),
    ('education_support', 'Education Support'),
    ('health_support', 'Health Support'),
    ('cultural', 'Cultural & Heritage'),
    ('tourism', 'Tourism Development'),
    ('disaster_management', 'Disaster Management'),
    ('other', 'Other'),
]


class NonInfrastructureProjectForm(forms.Form):
    title = forms.CharField(required=True, max_length=255)
    project_type = forms.ChoiceField(
        # Defaults preserve compatibility with older form posts and records.
        required=False,
        choices=NonInfrastructureProject.ProjectType.choices,
        initial=NonInfrastructureProject.ProjectType.EVENT,
        label='Project Type',
    )
    description = forms.CharField(required=True, widget=forms.Textarea(attrs={'rows': 4}), max_length=2000)
    category = forms.ModelChoiceField(
        queryset=NonInfrastructureCategory.objects.none(),
        required=True,
        empty_label='Select Category',
    )

    proponent = forms.CharField(required=True, max_length=255, label='Implementing Office')
    target_beneficiaries = forms.CharField(
        required=False, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}),
    )
    beneficiaries = forms.IntegerField(required=False, min_value=0, label='Number of Beneficiaries')
    implementation_start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    implementation_end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    event_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    start_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    end_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    venue_name = forms.CharField(required=False, max_length=255)
    project_cost = forms.DecimalField(required=False, min_value=0, max_digits=15, decimal_places=2, label='Budget / Project Cost')
    fund_source = forms.CharField(required=False, max_length=255)
    contractor_supplier = forms.CharField(required=False, max_length=255, label='Contractor / Supplier')
    procurement_description = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}), label='Item / Procurement Description')
    quantity = forms.IntegerField(required=False, min_value=1)
    expected_delivery_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    remarks = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))
    street = forms.CharField(required=False, max_length=500)
    barangay = forms.ChoiceField(
        required=True,
        choices=[('', 'Select Barangay')] + list(BARANGAY_CHOICES),
        widget=forms.Select,
    )
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
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

        self._ensure_categories_exist()
        self.fields['category'].queryset = NonInfrastructureCategory.objects.all().order_by('type_name')

        self.fields['municipality'].initial = 'Gabaldon'
        self.fields['province'].initial = 'Nueva Ecija'
        self.fields['municipality'].widget.attrs['readonly'] = 'readonly'
        self.fields['province'].widget.attrs['readonly'] = 'readonly'

        if self.instance is not None:
            normalized = self._resolve_instance(self.instance)
            if normalized is not None:
                self.existing_images = list(
                    normalized.project.images.order_by('-is_cover', '-created_at')
                )
                existing_cover = next(
                    (image for image in self.existing_images if image.is_cover),
                    self.existing_images[0] if self.existing_images else None,
                )
                if existing_cover:
                    self.fields['cover_image_selection'].initial = (
                        f'existing:{existing_cover.pk}'
                    )
                self.fields['title'].initial = normalized.title
                self.fields['project_type'].initial = normalized.project_type
                self.fields['description'].initial = normalized.description
                self.fields['category'].initial = normalized.category_id
                self.fields['proponent'].initial = normalized.proponent
                self.fields['beneficiaries'].initial = normalized.beneficiaries
                self.fields['target_beneficiaries'].initial = normalized.target_beneficiaries
                self.fields['implementation_start_date'].initial = normalized.implementation_start_date
                self.fields['implementation_end_date'].initial = normalized.implementation_end_date
                self.fields['event_date'].initial = normalized.event_date
                self.fields['start_time'].initial = normalized.start_time
                self.fields['end_time'].initial = normalized.end_time
                self.fields['venue_name'].initial = normalized.venue_name
                self.fields['project_cost'].initial = normalized.project_cost
                self.fields['fund_source'].initial = normalized.fund_source
                self.fields['contractor_supplier'].initial = normalized.contractor_supplier
                self.fields['procurement_description'].initial = normalized.procurement_description
                self.fields['quantity'].initial = normalized.quantity
                self.fields['expected_delivery_date'].initial = normalized.expected_delivery_date
                self.fields['remarks'].initial = normalized.remarks
                if normalized.address:
                    self.fields['street'].initial = normalized.address.street
                    self.fields['barangay'].initial = normalized.address.barangay
                    self.fields['municipality'].initial = normalized.address.municipality or 'Gabaldon'
                    self.fields['province'].initial = normalized.address.province or 'Nueva Ecija'

    @staticmethod
    def _ensure_categories_exist():
        for code, name in NON_INFRA_CATEGORY_DEFAULTS:
            NonInfrastructureCategory.objects.get_or_create(
                type_code=code,
                defaults={'type_name': name, 'description': name},
            )

    def clean_municipality(self):
        return 'Gabaldon'

    def clean_province(self):
        return 'Nueva Ecija'

    def clean(self):
        cleaned_data = super().clean()
        project_type = (
            cleaned_data.get('project_type')
            or NonInfrastructureProject.ProjectType.EVENT
        )
        cleaned_data['project_type'] = project_type
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        if project_type == NonInfrastructureProject.ProjectType.EVENT:
            for field_name in ('event_date', 'start_time', 'end_time', 'venue_name'):
                if not cleaned_data.get(field_name):
                    self.add_error(field_name, 'This field is required for an Event / Activity project.')
        elif project_type == NonInfrastructureProject.ProjectType.TRAINING:
            if not (
                cleaned_data.get('event_date')
                or cleaned_data.get('implementation_start_date')
            ):
                self.add_error(
                    'event_date',
                    'Provide a training date or an implementation start date.',
                )
            if not cleaned_data.get('venue_name'):
                self.add_error('venue_name', 'Venue is required for a Training / Seminar project.')
            if not cleaned_data.get('target_beneficiaries'):
                self.add_error(
                    'target_beneficiaries',
                    'Target participants are required for a Training / Seminar project.',
                )

        implementation_start = cleaned_data.get('implementation_start_date')
        implementation_end = cleaned_data.get('implementation_end_date')
        if implementation_start and implementation_end and implementation_end < implementation_start:
            self.add_error(
                'implementation_end_date',
                'Implementation end date cannot be earlier than the start date.',
            )

        if start_time and end_time and end_time <= start_time:
            self.add_error(
                'end_time',
                'End time must be later than the start time.',
            )

        return cleaned_data

    @staticmethod
    def _resolve_instance(instance):
        return instance if isinstance(instance, NonInfrastructureProject) else None

    def _save_images(self, project):

        cover_selection = self.cleaned_data.get(
            'cover_image_selection',
            '',
        )

        images_to_delete = self.cleaned_data.get('images_to_delete', '')

        if images_to_delete:
            image_ids = []

            for image_id in images_to_delete.split(','):
                image_id = image_id.strip()
                if image_id.isdigit():
                    image_ids.append(int(image_id))

            if image_ids:
                retire_project_images(project, image_ids)

        uploaded_files = []

        if hasattr(self, 'files') and self.files:
            raw_files = (
                self.files.getlist('project_images')
                if hasattr(self.files, 'getlist')
                else self.files.get('project_images', [])
            )

            if isinstance(raw_files, (list, tuple)):
                uploaded_files = raw_files
            else:
                uploaded_files = [raw_files]

        saved_images = []

        for upload in uploaded_files:
            if not upload or not getattr(upload, 'name', None):
                continue

            folder = os.path.join('projects', str(project.project_id))
            filename = default_storage.save(
                os.path.join(folder, upload.name),
                upload,
            )
            file_url = default_storage.url(filename)

            saved_images.append(
                ProjectImage.objects.create(
                    project=project,
                    image_url=file_url,
                )
            )

        selected_cover = None

        if cover_selection.startswith('existing:'):
            image_id = cover_selection.removeprefix('existing:')
            if image_id.isdigit():
                selected_cover = project.images.filter(pk=int(image_id)).first()
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

        if instance is not None:
            normalized_instance = self._resolve_instance(instance)
            if normalized_instance is not None:
                project = normalized_instance.project
                non = normalized_instance
            else:
                project = Project.objects.create(
                    project_type='non_infrastructure',
                    created_by_user=user,
                    updated_by_user=user,
                )
                non = NonInfrastructureProject.objects.create(project=project)
        else:
            project = Project.objects.create(
                project_type='non_infrastructure',
                created_by_user=user,
                updated_by_user=user,
            )
            non = NonInfrastructureProject.objects.filter(project=project).first()
            if non is None:
                non = NonInfrastructureProject(project=project)

        non.title = data.get('title') or non.title
        non.project_type = data.get('project_type') or non.project_type
        non.description = data.get('description') or ''
        non.category = data.get('category')
        non.proponent = data.get('proponent') or ''
        non.beneficiaries = data.get('beneficiaries')
        non.target_beneficiaries = data.get('target_beneficiaries') or ''
        non.implementation_start_date = data.get('implementation_start_date')
        non.implementation_end_date = data.get('implementation_end_date')
        non.event_date = data.get('event_date')
        non.start_time = data.get('start_time')
        non.end_time = data.get('end_time')
        non.venue_name = data.get('venue_name') or ''
        non.project_cost = data.get('project_cost')
        non.fund_source = data.get('fund_source') or ''
        non.contractor_supplier = data.get('contractor_supplier') or ''
        non.procurement_description = data.get('procurement_description') or ''
        non.quantity = data.get('quantity')
        non.expected_delivery_date = data.get('expected_delivery_date')
        non.remarks = data.get('remarks') or ''

        street = data.get('street') or ''
        barangay = data.get('barangay') or ''
        municipality = 'Gabaldon'
        province = 'Nueva Ecija'

        if street or barangay or municipality or province:
            if non.address:
                addr = non.address
            else:
                addr = Address.objects.create(
                    street=street,
                    barangay=barangay,
                    municipality=municipality,
                    province=province,
                )
                non.address = addr

            addr.street = street or addr.street
            addr.barangay = barangay or addr.barangay
            addr.municipality = municipality or addr.municipality
            addr.province = province or addr.province
            addr.save()
            non.address = addr

        non.save()
        self._save_images(project)
        return non


class NonInfrastructureOperationalForm(forms.ModelForm):
    class Meta:
        model = NonInfrastructureProject
        fields = ['status']

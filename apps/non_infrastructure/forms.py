import os

from django import forms
from django.core.files.storage import default_storage

from apps.non_infrastructure.models import NonInfrastructureProject as LegacyNonInfrastructureProject
from apps.system.models import (
    Address,
    NonInfrastructureCategory,
    Non_Infrastructure_Project,
    Project,
    Project_Image,
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
    non_infra_name = forms.CharField(required=True, max_length=255)
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4}), max_length=2000)
    non_infra_category = forms.ModelChoiceField(
        queryset=NonInfrastructureCategory.objects.none(),
        required=False,
        empty_label='Select Category',
    )

    status = forms.ChoiceField(
        required=True,
        choices=Non_Infrastructure_Project.STATUS_CHOICES,
        widget=forms.Select,
    )

    proponent = forms.CharField(required=False, max_length=255)
    beneficiaries = forms.IntegerField(required=False, min_value=0)
    event_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    start_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    end_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    venue_name = forms.CharField(required=False, max_length=255)
    street = forms.CharField(required=False, max_length=500)
    barangay = forms.ChoiceField(
        required=False,
        choices=[('', 'Select Barangay')] + list(LegacyNonInfrastructureProject.LOCATION_CHOICES),
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

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

        self._ensure_categories_exist()
        self.fields['non_infra_category'].queryset = NonInfrastructureCategory.objects.all().order_by('type_name')

        self.fields['municipality'].initial = 'Gabaldon'
        self.fields['province'].initial = 'Nueva Ecija'
        self.fields['municipality'].widget.attrs['readonly'] = 'readonly'
        self.fields['province'].widget.attrs['readonly'] = 'readonly'

        if self.instance is not None:
            normalized = self._resolve_instance(self.instance)
            if normalized is not None:
                self.existing_images = list(normalized.project.images.order_by('-created_at'))
                self.fields['non_infra_name'].initial = normalized.non_infra_name
                self.fields['description'].initial = normalized.description
                self.fields['non_infra_category'].initial = normalized.non_infra_category_id
                self.fields['status'].initial = normalized.status
                self.fields['proponent'].initial = normalized.proponent
                self.fields['beneficiaries'].initial = normalized.beneficiaries
                self.fields['event_date'].initial = normalized.event_date
                self.fields['start_time'].initial = normalized.start_time
                self.fields['end_time'].initial = normalized.end_time
                self.fields['venue_name'].initial = normalized.venue_name
                if normalized.address:
                    self.fields['street'].initial = normalized.address.street
                    self.fields['barangay'].initial = normalized.address.barangay
                    self.fields['municipality'].initial = normalized.address.municipality or 'Gabaldon'
                    self.fields['province'].initial = normalized.address.province or 'Nueva Ecija'
                else:
                    self.existing_images = []

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

    @staticmethod
    def _resolve_instance(instance):
        if isinstance(instance, Non_Infrastructure_Project):
            return instance
        non_infra_id = getattr(instance, 'non_infra_id', None)
        if non_infra_id is None:
            return None
        return (
            Non_Infrastructure_Project.objects
            .select_related('project', 'address', 'non_infra_category')
            .filter(non_infra_id=non_infra_id)
            .first()
        )

    def _save_images(self, project):

        images_to_delete = self.cleaned_data.get('images_to_delete', '')

        if images_to_delete:
            image_ids = []

            for image_id in images_to_delete.split(','):
                
                image_id = image_id.strip()

                if image_id.isdigit():
                    image_ids.append(int(image_id))
            
            if image_ids:
                project.images.filter(
                    pk__in=image_ids
                ).delete()
            
        uploaded_files = []

        if hasattr(self, 'files') and self.files:

            raw_files = (
                self.files.getlist('project_images')
                if hasattr(self.files, 'getlist')
                else self.files.get(
                    'project_images',
                    []
                )
            )

            if isinstance(raw_files, (list, tuple)):
                uploaded_files = raw_files
            else:
                uploaded_files = [raw_files]


        # Nothing new was uploaded.
        # Existing images have already been processed above.
        if not uploaded_files:
            return


        # =====================================================
        # Save new images
        # =====================================================

        for upload in uploaded_files:

            if not upload or not getattr(
                upload,
                'name',
                None
            ):
                continue

            folder = os.path.join(
                'projects',
                str(project.project_id)
            )

            filename = default_storage.save(
                os.path.join(
                    folder,
                    upload.name
                ),
                upload
            )

            file_url = default_storage.url(
                filename
            )

            Project_Image.objects.create(
                project=project,
                image_url=file_url
            )

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
                non = Non_Infrastructure_Project.objects.create(project=project)
        else:
            project = Project.objects.create(
                project_type='non_infrastructure',
                created_by_user=user,
                updated_by_user=user,
            )
            non = Non_Infrastructure_Project.objects.filter(project=project).first()
            if non is None:
                non = Non_Infrastructure_Project(project=project)

        non.non_infra_name = data.get('non_infra_name') or non.non_infra_name
        non.description = data.get('description') or ''
        non.non_infra_category = data.get('non_infra_category')
        non.status = data.get('status') or non.status
        non.proponent = data.get('proponent') or ''
        non.beneficiaries = data.get('beneficiaries')
        non.event_date = data.get('event_date')
        non.start_time = data.get('start_time')
        non.end_time = data.get('end_time')
        non.venue_name = data.get('venue_name') or ''

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


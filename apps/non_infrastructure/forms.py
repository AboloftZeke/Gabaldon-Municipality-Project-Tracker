from django import forms

from apps.system.models import (
    Address,
    NonInfrastructureCategory,
    Non_Infrastructure_Project,
    Project,
    Project_Image,
)


class NonInfrastructureProjectForm(forms.Form):
    non_infra_name = forms.CharField(required=True, max_length=255)
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4}), max_length=2000)
    non_infra_category = forms.ModelChoiceField(
        queryset=NonInfrastructureCategory.objects.all().order_by('type_name'),
        required=False,
        empty_label='Select Category',
    )
    event_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    start_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    end_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    venue_name = forms.CharField(required=False, max_length=255)
    street = forms.CharField(required=False, max_length=500)
    barangay = forms.CharField(required=False, max_length=200)
    municipality = forms.CharField(required=False, max_length=200)
    province = forms.CharField(required=False, max_length=200)
    latitude = forms.DecimalField(required=False, max_digits=10, decimal_places=7)
    longitude = forms.DecimalField(required=False, max_digits=10, decimal_places=7)
    project_images = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Paste one image URL per line\nhttps://example.com/image-1.jpg\nhttps://example.com/image-2.jpg',
        }),
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

        if self.instance is not None:
            normalized = self._resolve_instance(self.instance)
            if normalized is not None:
                self.fields['non_infra_name'].initial = normalized.non_infra_name
                self.fields['description'].initial = normalized.description
                self.fields['non_infra_category'].initial = normalized.non_infra_category_id
                self.fields['event_date'].initial = normalized.event_date
                self.fields['start_time'].initial = normalized.start_time
                self.fields['end_time'].initial = normalized.end_time
                self.fields['venue_name'].initial = normalized.venue_name
                if normalized.address:
                    self.fields['street'].initial = normalized.address.street
                    self.fields['barangay'].initial = normalized.address.barangay
                    self.fields['municipality'].initial = normalized.address.municipality
                    self.fields['province'].initial = normalized.address.province
                    self.fields['latitude'].initial = normalized.address.latitude
                    self.fields['longitude'].initial = normalized.address.longitude
                image_urls = [img.image_url for img in normalized.project.images.all() if img.image_url]
                if image_urls:
                    self.fields['project_images'].initial = '\n'.join(image_urls)

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
        raw_images = self.cleaned_data.get('project_images') or ''
        urls = []
        for line in raw_images.replace(',', '\n').splitlines():
            value = line.strip()
            if value:
                urls.append(value)

        project.images.all().delete()
        for url in urls:
            Project_Image.objects.create(project=project, image_url=url)

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
        non.event_date = data.get('event_date')
        non.start_time = data.get('start_time')
        non.end_time = data.get('end_time')
        non.venue_name = data.get('venue_name') or ''

        street = data.get('street') or ''
        barangay = data.get('barangay') or ''
        municipality = data.get('municipality') or 'Gabaldon'
        province = data.get('province') or 'Nueva Ecija'
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if street or barangay or municipality or province or latitude is not None or longitude is not None:
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
            addr.latitude = latitude if latitude is not None else addr.latitude
            addr.longitude = longitude if longitude is not None else addr.longitude
            addr.save()
            non.address = addr

        non.save()
        self._save_images(project)
        return non


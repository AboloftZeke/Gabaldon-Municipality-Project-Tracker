from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.utils import timezone
import uuid

from .publication_workflow import PublicationStatus


class LoginOTPChallenge(models.Model):
    """Short-lived, hashed email verification challenge for a pending login."""

    challenge_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='login_otp_challenges',
    )
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts_remaining = models.PositiveSmallIntegerField(default=5)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'system_login_otp_challenge'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['expires_at', 'consumed_at']),
        ]

    def __str__(self):
        return f'Login verification for user {self.user_id}'


class Address(models.Model):
    """Normalized location data for migrated project records."""
    address_id = models.BigAutoField(primary_key=True)
    street = models.CharField(max_length=500, blank=True, null=True)
    barangay = models.CharField(max_length=200, blank=True, null=True)
    municipality = models.CharField(max_length=200, blank=True, null=True)
    province = models.CharField(max_length=200, blank=True, null=True)
    country = models.CharField(max_length=200, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'system_address'
        verbose_name = 'Address'
        verbose_name_plural = 'Addresses'

    def __str__(self):
        location_parts = [self.barangay, self.municipality, self.province]
        return ', '.join(filter(None, location_parts)) or f'Address {self.address_id}'


class Project(models.Model):
    """Base normalized project model for infrastructure and non-infrastructure records."""
    project_id = models.BigAutoField(primary_key=True)
    project_type = models.CharField(max_length=50, default='gallery')
    created_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='projects_created_by_user'
    )
    updated_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='projects_updated_by_user'
    )
    is_published = models.BooleanField(default=False)
    is_visible_to_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_project'
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'
        ordering = ['-created_at']

    def __str__(self):
        return f'Project {self.project_id} ({self.project_type})'


class ProjectRevision(models.Model):
    """Public-facing snapshot submitted through the review flow."""

    revision_id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='revisions',
    )
    revision_number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=30,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
    )
    snapshot = models.JSONField(default=dict)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    previous_revision = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='superseded_by_revisions',
    )
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submitted_project_revisions',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_project_revisions',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, default='')
    published_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='published_project_revisions',
    )
    published_at = models.DateTimeField(null=True, blank=True)
    is_current_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_project_revision'
        ordering = ['-revision_number']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'revision_number'],
                name='unique_project_publication_revision_number',
            ),
            models.UniqueConstraint(
                fields=['project'],
                condition=models.Q(is_current_public=True),
                name='one_current_public_revision_per_project',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_current_public=False)
                    | models.Q(status=PublicationStatus.PUBLISHED)
                ),
                name='current_public_revision_must_be_published',
            ),
        ]

    def __str__(self):
        return (
            f'Project {self.project_id} publication revision '
            f'{self.revision_number}'
        )


class UserRole(models.Model):
    """Persisted office and role assignment used for account authorization."""
    DEPARTMENT_CHOICES = [
        ('engineer', 'Engineering Office'),
        ('mayor', "Mayor's Office"),
        ('admin', 'Administration'),
    ]

    class Role(models.TextChoices):
        STAFF = 'staff', 'Staff'
        HEAD = 'head', 'Head'
        ADMIN = 'admin', 'Admin'

    id = models.BigAutoField(primary_key=True)
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='role_assignment')
    department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        default='admin',
        blank=True,
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default='',
        blank=True,
        help_text='Office responsibility used with department for authorization.',
    )

    def clean(self):
        super().clean()
        # Existing callers supply only department. Empty is an input default,
        # never a persisted role (also enforced by the database constraint).
        if not self.role:
            self.role = self.Role.ADMIN if self.department == 'admin' else self.Role.STAFF
        valid = (
            (self.department == 'admin' and self.role == self.Role.ADMIN)
            or (self.department in {'engineer', 'mayor'} and self.role in {self.Role.STAFF, self.Role.HEAD})
            # Preserve the pre-existing blank department without granting access.
            or (self.department == '' and self.role == self.Role.STAFF)
        )
        if not valid:
            raise ValidationError({'role': 'Select a role valid for this department.'})

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and not update_fields:
            return
        writes_department = update_fields is None or 'department' in update_fields
        if self.pk and writes_department:
            previous = type(self).objects.using(kwargs.get('using') or self._state.db).filter(pk=self.pk).values('department', 'role').first()
            if (
                previous and previous['department'] != self.department
                and previous['role'] == self.role
                and ('admin' in {previous['department'], self.department})
            ):
                # Preserve department-only account edits until forms expose roles.
                self.role = self.Role.ADMIN if self.department == 'admin' else self.Role.STAFF
        self.clean()
        if update_fields is not None and writes_department:
            kwargs['update_fields'] = set(update_fields) | {'role'}
        return super().save(*args, **kwargs)

    class Meta:
        db_table = 'system_user_role'
        verbose_name = 'User Role'
        verbose_name_plural = 'User Roles'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(department='admin', role='admin')
                    | models.Q(department__in=['engineer', 'mayor'], role__in=['staff', 'head'])
                    | models.Q(department='', role='staff')
                ),
                name='user_role_valid_department_role',
            ),
        ]

    def __str__(self):
        return f'{self.user.username} role'


class InfrastructureCategory(models.Model):
    """Normalized infrastructure category lookup."""
    infrastructure_category_id = models.BigAutoField(primary_key=True)
    category_code = models.CharField(max_length=100, unique=True)
    category_name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'system_infrastructure_category'
        verbose_name = 'Infrastructure Category'
        verbose_name_plural = 'Infrastructure Categories'

    def __str__(self):
        return self.category_name


class NonInfrastructureCategory(models.Model):
    """Normalized non-infrastructure category lookup."""
    non_infrastructure_category_id = models.BigAutoField(primary_key=True)
    type_code = models.CharField(max_length=100, unique=True)
    type_name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_non_infrastructure_category'
        verbose_name = 'Non-Infrastructure Category'
        verbose_name_plural = 'Non-Infrastructure Categories'

    def __str__(self):
        return self.type_name


class Contractor(models.Model):
    """Normalized contractor lookup."""
    contractor_id = models.BigAutoField(primary_key=True)
    contractor_name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_contractor'
        verbose_name = 'Contractor'
        verbose_name_plural = 'Contractors'

    def __str__(self):
        return self.contractor_name


class ImplementingOffice(models.Model):
    """Normalized implementing office lookup."""
    office_id = models.BigAutoField(primary_key=True)
    office_name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_implementing_office'
        verbose_name = 'Implementing Office'
        verbose_name_plural = 'Implementing Offices'

    def __str__(self):
        return self.office_name


class FundSource(models.Model):
    """Normalized funding source lookup."""
    fund_source_id = models.BigAutoField(primary_key=True)
    fund_source_code = models.CharField(max_length=100, unique=True)
    fund_source_name = models.CharField(max_length=255, unique=True)
    fund_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'system_fund_source'
        verbose_name = 'Fund Source'
        verbose_name_plural = 'Fund Sources'

    def __str__(self):
        return self.fund_source_name


class InfrastructureProject(models.Model):
    """Normalized infrastructure project details linked to the base Project model."""
    PROCUREMENT_METHOD_CHOICES = [
        ('competitive_bidding', 'Competitive Bidding / Public Bidding'),
        ('svp', 'SVP (Small Value Procurement)'),
        ('nq', 'NQ (Negotiated Quotation)'),
        ('shopping', 'Shopping'),
        ('direct_contracting', 'Direct Contracting'),
        ('force_account', 'Force Account'),
    ]

    STATUS_CHOICES = [
        ('not_yet_started', 'Not Yet Started'),
        ('ongoing', 'Ongoing'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
    ]

    infrastructure_id = models.BigAutoField(primary_key=True)
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='infrastructure_project'
    )
    infrastructure_code = models.CharField(max_length=150, unique=True, null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    category = models.ForeignKey(
        InfrastructureCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='infrastructure_projects'
    )
    address = models.ForeignKey(
        Address,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='infrastructure_projects'
    )
    contractor = models.ForeignKey(
        Contractor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='infrastructure_projects'
    )
    implementing_office = models.ForeignKey(
        ImplementingOffice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='infrastructure_projects'
    )
    procurement_method = models.CharField(
        max_length=50,
        choices=PROCUREMENT_METHOD_CHOICES,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        db_column='award_status',
        null=True,
        blank=True,
    )
    planned_start_date = models.DateField(null=True, blank=True)
    planned_end_date = models.DateField(null=True, blank=True)
    cost_progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    physical_progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_infrastructure_project'
        verbose_name = 'Infrastructure Project'
        verbose_name_plural = 'Infrastructure Projects'
        ordering = ['-created_at']

    def __str__(self):
        return self.title



class InfrastructureProgressUpdate(models.Model):
    progress_update_id = models.BigAutoField(primary_key=True)
    infrastructure = models.ForeignKey(
        InfrastructureProject,
        on_delete=models.CASCADE,
        related_name='progress_updates',
    )
    previous_official_status = models.CharField(
        max_length=50,
        choices=InfrastructureProject.STATUS_CHOICES,
        blank=True,
        default='',
    )
    new_official_status = models.CharField(
        max_length=50,
        choices=InfrastructureProject.STATUS_CHOICES,
        blank=True,
        default='',
    )
    previous_physical_progress = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    new_physical_progress = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    head_remarks = models.TextField(blank=True, default='')
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='infrastructure_progress_updates',
    )
    supporting_inspections = models.ManyToManyField(
        'ProjectInspection',
        blank=True,
        related_name='supported_progress_updates',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'system_infrastructure_progress_update'
        verbose_name = 'Infrastructure Progress Update'
        verbose_name_plural = 'Infrastructure Progress Updates'
        ordering = ('-created_at', '-progress_update_id')

    def __str__(self):
        return f'{self.infrastructure} progress update {self.progress_update_id}'


class NonInfrastructureProject(models.Model):
    """Normalized non-infrastructure project details linked to the base Project model."""
    class ProjectType(models.TextChoices):
        EVENT = 'EVENT', 'Event / Activity'
        PROGRAM = 'PROGRAM', 'Program'
        SERVICE = 'SERVICE', 'Service'
        PROCUREMENT = 'PROCUREMENT', 'Procurement / Acquisition'
        TRAINING = 'TRAINING', 'Training / Seminar'
        CAMPAIGN = 'CAMPAIGN', 'Campaign / Initiative'
        OTHER = 'OTHER', 'Other'

    non_infra_id = models.BigAutoField(primary_key=True)
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='non_infrastructure_project'
    )
    title = models.CharField(max_length=255)
    category = models.ForeignKey(
        NonInfrastructureCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='non_infrastructure_projects'
    )
    # Existing records were created through the event-oriented form.  Keep
    # them compatible by treating their unspecified type as an event.
    project_type = models.CharField(
        max_length=20,
        choices=ProjectType.choices,
        default=ProjectType.EVENT,
    )
    event_date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    venue_name = models.CharField(max_length=255, blank=True, null=True)
    proponent = models.CharField(max_length=255, blank=True, default='')
    beneficiaries = models.IntegerField(null=True, blank=True)
    target_beneficiaries = models.TextField(blank=True, default='')
    implementation_start_date = models.DateField(null=True, blank=True)
    implementation_end_date = models.DateField(null=True, blank=True)
    project_cost = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
    )
    fund_source = models.CharField(max_length=255, blank=True, default='')
    contractor_supplier = models.CharField(
        max_length=255, blank=True, default='',
    )
    procurement_description = models.TextField(blank=True, default='')
    quantity = models.PositiveIntegerField(null=True, blank=True)
    expected_delivery_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True, default='')
    address = models.ForeignKey(
        Address,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='non_infrastructure_projects'
    )
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_non_infrastructure_project'
        verbose_name = 'Non-Infrastructure Project'
        verbose_name_plural = 'Non-Infrastructure Projects'
        ordering = ['-created_at']

    def __str__(self):
        return self.title
    
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed')
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')

    def clean(self):
        """Keep event-only schedule requirements consistent outside the form."""
        errors = {}
        if self.project_type == self.ProjectType.EVENT:
            for field_name in ('event_date', 'start_time', 'end_time', 'venue_name'):
                if not getattr(self, field_name):
                    errors[field_name] = (
                        'This field is required for an Event / Activity project.'
                    )
        elif self.project_type == self.ProjectType.TRAINING:
            if not (self.event_date or self.implementation_start_date):
                errors['event_date'] = (
                    'Provide a training date or an implementation start date.'
                )
            if not self.venue_name:
                errors['venue_name'] = (
                    'Venue is required for a Training / Seminar project.'
                )
            if not self.target_beneficiaries:
                errors['target_beneficiaries'] = (
                    'Target participants are required for a Training / Seminar project.'
                )
        if (
            self.implementation_start_date
            and self.implementation_end_date
            and self.implementation_end_date < self.implementation_start_date
        ):
            errors['implementation_end_date'] = (
                'Implementation end date cannot be earlier than the start date.'
            )
        if errors:
            raise ValidationError(errors)



class InfrastructureSchedule(models.Model):
    """Normalized schedule/timeline data for infrastructure projects."""
    schedule_id = models.BigAutoField(primary_key=True)
    infrastructure = models.ForeignKey(
        InfrastructureProject,
        on_delete=models.CASCADE,
        related_name='schedules'
    )
    pre_bid_date = models.DateField(null=True, blank=True)
    bidding_date = models.DateField(null=True, blank=True)
    notice_award_date = models.DateField(null=True, blank=True)
    notice_proceed_date = models.DateField(null=True, blank=True)
    posting_date = models.DateField(null=True, blank=True)
    duration_days = models.IntegerField(null=True, blank=True)
    contract_expiry_date = models.DateField(null=True, blank=True)
    actual_start_date = models.DateField(null=True, blank=True)
    actual_completion_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_infrastructure_schedule'
        verbose_name = 'Infrastructure Schedule'
        verbose_name_plural = 'Infrastructure Schedules'

    def __str__(self):
        return f'{self.infrastructure.title} schedule'


class FinancialRecord(models.Model):
    """Normalized financial values for infrastructure projects."""
    financial_id = models.BigAutoField(primary_key=True)
    infrastructure = models.ForeignKey(
        InfrastructureProject,
        on_delete=models.CASCADE,
        related_name='financial_records'
    )
    fund_source = models.ForeignKey(
        FundSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='finances'
    )
    approved_budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    bid_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    actual_expenditure = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    is_visible_to_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_financial_record'
        verbose_name = 'Financial Record'
        verbose_name_plural = 'Financial Records'

    def __str__(self):
        return f'{self.infrastructure.title} financial record'


class ProjectInspection(models.Model):
    """Normalized inspection/progress records for project entities."""
    INSPECTION_TYPE_CHOICES = [
        ('progress', 'Progress'),
        ('routine', 'Routine'),
        ('final', 'Final'),
        ('special', 'Special'),
    ]

    inspection_id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='inspections'
    )
    inspection_date = models.DateField()
    inspection_type = models.CharField(
        max_length=20,
        choices=INSPECTION_TYPE_CHOICES,
        default='routine',
    )
    inspected_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inspections_done'
    )
    completion_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    findings = models.TextField(blank=True, default='')
    remarks = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'system_project_inspection'
        verbose_name = 'Project Inspection'
        verbose_name_plural = 'Project Inspections'

    def __str__(self):
        return f'Inspection {self.inspection_id}'


class InspectionEvidence(models.Model):
    EVIDENCE_TYPE_CHOICES = [
        ('image', 'Photo'),
        ('document', 'Document'),
    ]

    inspection_evidence_id = models.BigAutoField(primary_key=True)
    inspection = models.ForeignKey(
        ProjectInspection,
        on_delete=models.CASCADE,
        related_name='evidence',
    )
    evidence_type = models.CharField(
        max_length=20,
        choices=EVIDENCE_TYPE_CHOICES,
    )
    original_name = models.CharField(max_length=255)
    storage_name = models.CharField(max_length=500)
    file_url = models.URLField(max_length=500)
    content_type = models.CharField(max_length=100, blank=True, default='')
    uploaded_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inspection_evidence_uploaded',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'system_inspection_evidence'
        verbose_name = 'Inspection Evidence'
        verbose_name_plural = 'Inspection Evidence'
        ordering = ('created_at', 'inspection_evidence_id')

    def __str__(self):
        return self.original_name


class ActiveProjectImageManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class ProjectImage(models.Model):
    """Simple project image metadata for the normalized ERD."""
    project_image_id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField(max_length=500, blank=True, null=True)
    is_cover = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    objects = ActiveProjectImageManager()
    all_objects = models.Manager()
    # Removed `image_name` and `caption` fields to simplify image storage.
    # Use `image_url` and `created_at` to identify/label images. Run migrations after this change.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_project_image'
        verbose_name = 'Project Image'
        verbose_name_plural = 'Project Images'
        constraints = [
            models.UniqueConstraint(
                fields=['project'],
                condition=models.Q(is_cover=True),
                name='unique_cover_image_per_project',
            ),
        ]


class ProjectReport(models.Model):
    """Project report metadata for the normalized ERD."""
    class ReportType(models.TextChoices):
        INFRASTRUCTURE_INDIVIDUAL = (
            'infrastructure_individual',
            'Infrastructure Individual',
        )
        NON_INFRASTRUCTURE_INDIVIDUAL = (
            'non_infrastructure_individual',
            'Non-Infrastructure Individual',
        )
        INFRASTRUCTURE_SUMMARY = (
            'infrastructure_summary',
            'Infrastructure Summary',
        )
        NON_INFRASTRUCTURE_SUMMARY = (
            'non_infrastructure_summary',
            'Non-Infrastructure Summary',
        )

    report_id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='reports',
        null=True,
        blank=True,
    )
    report_name = models.CharField(max_length=255)
    report_type = models.CharField(
        max_length=100,
        choices=ReportType.choices,
        blank=True,
        null=True,
    )
    file_url = models.URLField(max_length=500, blank=True, null=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_project_report'
        verbose_name = 'Report'
        verbose_name_plural = 'Project Reports'


class ReportTemplate(models.Model):
    """Reusable report templates for the normalized ERD."""
    template_id = models.BigAutoField(primary_key=True)
    template_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    file_url = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_report_template'
        verbose_name = 'Report Template'
        verbose_name_plural = 'Report Templates'

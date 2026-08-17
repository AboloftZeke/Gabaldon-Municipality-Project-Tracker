from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserProfile(models.Model):
    """
    Compatibility model that now points at the archive table created during the safe cleanup migration.
    """
    DEPARTMENT_CHOICES = [
        ('engineer', 'Engineering Office'),
        ('mayor', "Mayor's Office"),
        ('admin', 'Administration'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        default='admin'
    )

    must_change_password = models.BooleanField(
        default=False,
        help_text="Require the user to change their password upon next login."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_department_display()}"

    @classmethod
    def department_for_user(cls, user):
        """Compatibility helper for access patterns that still rely on the legacy profile table."""
        # Runtime should no longer depend on the archived profile table.
        # Prefer the explicit department stored in the persisted compatibility
        # flag or runtime profile. Only fall back to the Django staff flag when no
        # explicit department is available.
        if user is None:
            return None
        if getattr(user, 'is_superuser', False):
            return 'admin'

        try:
            from apps.system.models import UserFlag
            flag = UserFlag.objects.filter(user=user).first()
            if flag and getattr(flag, 'department', None):
                return flag.department
        except Exception:
            pass

        profile = getattr(user, 'profile', None)
        if profile is not None:
            department = getattr(profile, 'department', None)
            if department:
                return department
        if getattr(user, 'is_staff', False):
            return 'engineer'
        return 'mayor'

    @classmethod
    def profile_for_user(cls, user):
        """Get the legacy user profile without relying on a direct OneToOne access pattern."""
        # Return a lightweight compatibility object instead of hitting the archive table.
        if user is None:
            return None
        class _P:
            def __init__(self, user):
                self.user = user
                self.department = cls.department_for_user(user)
                self.must_change_password = False
        return _P(user)

    class Meta:
        managed = False
        db_table = 'system_legacy_userprofile_archive'
        ordering = ['user__username']


class PasswordChangeHistory(models.Model):
    """
    Compatibility model pointing at the archived password change log.
    """
    CHANGE_METHOD_CHOICES = [
        ('creation', 'User Creation'),
        ('reset_link', 'Password Reset Link'),
        ('admin_edit', 'Admin Edit'),
        ('user_edit', 'User Self-Edit'),
        ('signal', 'System Change'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='password_changes'
    )

    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='password_changes_made'
    )

    method = models.CharField(
        max_length=20,
        choices=CHANGE_METHOD_CHOICES,
        default='signal'
    )

    notes = models.TextField(blank=True, default='')

    class Meta:
        managed = False
        db_table = 'system_legacy_passwordchangehistory_archive'
        ordering = ['-changed_at']
        verbose_name_plural = 'Password Change History'
        indexes = [
            models.Index(fields=['-changed_at']),
            models.Index(fields=['user', '-changed_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_method_display()} - {self.changed_at.strftime('%Y-%m-%d %H:%M')}"


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
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'
        ordering = ['-created_at']

    def __str__(self):
        return f'Project {self.project_id} ({self.project_type})'


class UserFlag(models.Model):
    """Persistent runtime flags for users without reintroducing legacy profile."""
    DEPARTMENT_CHOICES = [
        ('engineer', 'Engineering Office'),
        ('mayor', "Mayor's Office"),
        ('admin', 'Administration'),
    ]

    id = models.BigAutoField(primary_key=True)
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='flags')
    must_change_password = models.BooleanField(default=False)
    department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        default='admin',
        blank=True,
    )

    class Meta:
        verbose_name = 'User Flag'
        verbose_name_plural = 'User Flags'

    def __str__(self):
        return f'{self.user.username} flags'


class InfrastructureCategory(models.Model):
    """Normalized infrastructure category lookup."""
    infrastructure_category_id = models.BigAutoField(primary_key=True)
    category_code = models.CharField(max_length=100, unique=True)
    category_name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
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
        verbose_name = 'Fund Source'
        verbose_name_plural = 'Fund Sources'

    def __str__(self):
        return self.fund_source_name


class Infrastructure_Project(models.Model):
    """Normalized infrastructure project details linked to the base Project model."""
    PROCUREMENT_METHOD_CHOICES = [
        ('competitive_bidding', 'Competitive Bidding / Public Bidding'),
        ('svp', 'SVP (Small Value Procurement)'),
        ('nq', 'NQ (Negotiated Quotation)'),
        ('shopping', 'Shopping'),
        ('direct_contracting', 'Direct Contracting'),
        ('force_account', 'Force Account'),
    ]

    AWARD_STATUS_CHOICES = [
        ('awarded', 'Awarded'),
        ('ongoing_bidding', 'Ongoing Bidding'),
        ('cancelled', 'Cancelled'),
        ('rebid', 'Re-bid'),
        ('completed', 'Completed'),
    ]

    infrastructure_id = models.BigAutoField(primary_key=True)
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='infrastructure_project'
    )
    infrastructure_code = models.CharField(max_length=150, unique=True, null=True, blank=True)
    infrastructure_title = models.CharField(max_length=255)
    infrastructure_description = models.TextField(blank=True, default='')
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
    award_status = models.CharField(
        max_length=50,
        choices=AWARD_STATUS_CHOICES,
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
        verbose_name = 'Infrastructure Project'
        verbose_name_plural = 'Infrastructure Projects'
        ordering = ['-created_at']

    def __str__(self):
        return self.infrastructure_title

    # Compatibility properties to match legacy InfrastructureProject attribute names
    @property
    def title(self):
        return self.infrastructure_title

    @title.setter
    def title(self, value):
        self.infrastructure_title = value

    @property
    def description(self):
        return self.infrastructure_description

    @description.setter
    def description(self, value):
        self.infrastructure_description = value

    @property
    def latitude(self):
        if self.address:
            return self.address.latitude
        return None

    @latitude.setter
    def latitude(self, value):
        if self.address:
            self.address.latitude = value
            self.address.save(update_fields=['latitude'])

    @property
    def longitude(self):
        if self.address:
            return self.address.longitude
        return None

    @longitude.setter
    def longitude(self, value):
        if self.address:
            self.address.longitude = value
            self.address.save(update_fields=['longitude'])

    @property
    def contractor(self):
        return self.contractor_id and (self.contractor.contractor_name if self.contractor else None)

    @contractor.setter
    def contractor(self, name):
        if name:
            if hasattr(name, 'contractor_id'):
                self.contractor_id = name.contractor_id
                return
            contractor_obj, _ = Contractor.objects.get_or_create(
                contractor_name=str(name).strip(),
                defaults={'is_active': True},
            )
            self.contractor_id = contractor_obj.contractor_id

    @property
    def implementing_office(self):
        return self.implementing_office_id and (self.implementing_office.office_name if self.implementing_office else None)

    @implementing_office.setter
    def implementing_office(self, name):
        if name:
            if hasattr(name, 'office_id'):
                self.implementing_office_id = name.office_id
                return
            office_obj, _ = ImplementingOffice.objects.get_or_create(
                office_name=str(name).strip(),
                defaults={'is_active': True},
            )
            self.implementing_office_id = office_obj.office_id

    @property
    def source_of_fund(self):
        # Return the first related fund source name if present
        fin = self.financial_records.first()
        return fin and fin.fund_source and fin.fund_source.fund_source_name or None

    @property
    def abc_amount(self):
        fin = self.financial_records.first()
        return fin and fin.approved_budget or None

    @property
    def contract_price(self):
        fin = self.financial_records.first()
        return fin and fin.bid_amount or None


class Non_Infrastructure_Project(models.Model):
    """Normalized non-infrastructure project details linked to the base Project model."""
    non_infra_id = models.BigAutoField(primary_key=True)
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='non_infrastructure_project'
    )
    non_infra_name = models.CharField(max_length=255)
    non_infra_category = models.ForeignKey(
        NonInfrastructureCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='non_infrastructure_projects'
    )
    event_date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    venue_name = models.CharField(max_length=255, blank=True, null=True)
    proponent = models.CharField(max_length=255, blank=True, default='')
    beneficiaries = models.IntegerField(null=True, blank=True)
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
        verbose_name = 'Non-Infrastructure Project'
        verbose_name_plural = 'Non-Infrastructure Projects'
        ordering = ['-created_at']

    def __str__(self):
        return self.non_infra_name


class Infrastructure_Schedule(models.Model):
    """Normalized schedule/timeline data for infrastructure projects."""
    schedule_id = models.BigAutoField(primary_key=True)
    infrastructure = models.ForeignKey(
        Infrastructure_Project,
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
        verbose_name = 'Infrastructure Schedule'
        verbose_name_plural = 'Infrastructure Schedules'

    def __str__(self):
        return f'{self.infrastructure.infrastructure_title} schedule'


class Financial(models.Model):
    """Normalized financial values for infrastructure projects."""
    financial_id = models.BigAutoField(primary_key=True)
    infrastructure = models.ForeignKey(
        Infrastructure_Project,
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
        verbose_name = 'Financial'
        verbose_name_plural = 'Financial Records'

    def __str__(self):
        return f'{self.infrastructure.infrastructure_title} financial record'


class Project_Inspection(models.Model):
    """Normalized inspection/progress records for project entities."""
    inspection_id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='inspections'
    )
    inspection_date = models.DateField()
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
        verbose_name = 'Project Inspection'
        verbose_name_plural = 'Project Inspections'

    def __str__(self):
        return f'Inspection {self.inspection_id}'


class Project_Image(models.Model):
    """Simple project image metadata for the normalized ERD."""
    project_image_id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField(max_length=500, blank=True, null=True)
    # Removed `image_name` and `caption` fields to simplify image storage.
    # Use `image_url` and `created_at` to identify/label images. Run migrations after this change.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Project Image'
        verbose_name_plural = 'Project Images'


class Reports(models.Model):
    """Project report metadata for the normalized ERD."""
    report_id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='reports')
    report_name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=100, blank=True, null=True)
    file_url = models.URLField(max_length=500, blank=True, null=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Report'
        verbose_name_plural = 'Reports'


class Reports_Template(models.Model):
    """Reusable report templates for the normalized ERD."""
    template_id = models.BigAutoField(primary_key=True)
    template_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    file_url = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Report Template'
        verbose_name_plural = 'Report Templates'


# Compatibility models shaped like the legacy models but mapped to the normalized tables.
class InfrastructureProject(models.Model):
    """Compatibility model exposing legacy field names but using the normalized infrastructure table."""
    id = models.BigAutoField(primary_key=True, db_column='infrastructure_id')
    title = models.CharField(max_length=255, db_column='infrastructure_title')
    description = models.TextField(db_column='infrastructure_description')
    # contractor and implementing office are stored as FKs in the normalized table.
    # Expose them as read-only compatibility properties instead of real model fields
    # so Django won't attempt to SELECT non-existent legacy columns on the
    # `system_infrastructure_project` compatibility table (managed=False).
    @property
    def contractor_id(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).select_related('contractor').first()
        return infra.contractor.contractor_id if infra and infra.contractor else None

    @property
    def implementing_office_id(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).select_related('implementing_office').first()
        return infra.implementing_office.office_id if infra and infra.implementing_office else None
    procurement_method = models.CharField(max_length=50, null=True, blank=True)
    award_status = models.CharField(max_length=50, null=True, blank=True)
    planned_start_date = models.DateField(null=True, blank=True)
    planned_end_date = models.DateField(null=True, blank=True)
    cost_progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    physical_progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        managed = False
        db_table = 'system_infrastructure_project'

    @property
    def created_by(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).select_related('project').first()
        return infra.project.created_by_user if infra and infra.project else None

    # Compatibility accessors for template/display helpers
    @property
    def location(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).select_related('address').first()
        if infra and infra.address and infra.address.barangay:
            return infra.address.barangay
        return ''

    @property
    def latitude(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).select_related('address').first()
        if infra and infra.address and infra.address.latitude is not None:
            return infra.address.latitude
        return None

    @property
    def longitude(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).select_related('address').first()
        if infra and infra.address and infra.address.longitude is not None:
            return infra.address.longitude
        return None

    def get_location_display(self):
        return self.location

    def get_category_display(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).select_related('category').first()
        return infra.category.category_name if infra and infra.category else ''

    def get_procurement_method_display(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).first()
        if infra and getattr(infra, 'procurement_method', None):
            return dict(Infrastructure_Project.PROCUREMENT_METHOD_CHOICES).get(infra.procurement_method, infra.procurement_method)
        return ''

    def get_award_status_display(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).first()
        if infra and getattr(infra, 'award_status', None):
            return dict(Infrastructure_Project.AWARD_STATUS_CHOICES).get(infra.award_status, infra.award_status)
        return ''

    @property
    def abc_amount(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).first()
        if infra:
            fin = infra.financial_records.first()
            return fin.approved_budget if fin else None
        return None

    @property
    def contract_price(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).first()
        if infra:
            fin = infra.financial_records.first()
            return fin.bid_amount if fin else None
        return None

    @property
    def cost_progress_percentage(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).first()
        return infra.cost_progress_percentage if infra and getattr(infra, 'cost_progress_percentage', None) is not None else None

    @property
    def physical_progress_percentage(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).first()
        return infra.physical_progress_percentage if infra and getattr(infra, 'physical_progress_percentage', None) is not None else None

    @property
    def contractor(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).first()
        contractor_id = getattr(infra, 'contractor_id', None) if infra else None
        if contractor_id:
            c = Contractor.objects.filter(contractor_id=contractor_id).first()
            return c.contractor_name if c else None
        return None

    @property
    def implementing_office(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).first()
        office_id = getattr(infra, 'implementing_office_id', None) if infra else None
        if office_id:
            o = ImplementingOffice.objects.filter(office_id=office_id).first()
            return o.office_name if o else None
        return None

    @property
    def source_of_fund(self):
        infra = Infrastructure_Project.objects.filter(infrastructure_id=self.id).first()
        if infra:
            fin = infra.financial_records.first()
            return fin.fund_source.fund_source_name if fin and fin.fund_source else None
        return None


class NonInfrastructureProject(models.Model):
    """Compatibility model for non-infrastructure mapped to normalized non-infra table."""
    non_infra_id = models.BigAutoField(primary_key=True, db_column='non_infra_id')
    non_infra_name = models.CharField(max_length=255, db_column='non_infra_name')
    event_date = models.DateField(null=True, blank=True, db_column='event_date')
    start_time = models.TimeField(null=True, blank=True, db_column='start_time')
    end_time = models.TimeField(null=True, blank=True, db_column='end_time')
    proponent = models.CharField(max_length=255, blank=True, default='', db_column='proponent')
    beneficiaries = models.IntegerField(null=True, blank=True, db_column='beneficiaries')
    description = models.TextField(db_column='description')
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        managed = False
        db_table = 'system_non_infrastructure_project'

    @property
    def title(self):
        return self.non_infra_name

    @title.setter
    def title(self, value):
        self.non_infra_name = value

    @property
    def location(self):
        normalized = Non_Infrastructure_Project.objects.filter(non_infra_id=self.non_infra_id).select_related('address').first()
        if normalized and normalized.address and normalized.address.barangay:
            return normalized.address.barangay
        return ''

    @property
    def category(self):
        normalized = Non_Infrastructure_Project.objects.filter(non_infra_id=self.non_infra_id).select_related('non_infra_category').first()
        if normalized and normalized.non_infra_category:
            return normalized.non_infra_category.type_name
        return ''

    def get_location_display(self):
        return self.location

    def get_category_display(self):
        return self.category

    @property
    def images(self):
        normalized = Non_Infrastructure_Project.objects.filter(non_infra_id=self.non_infra_id).select_related('project').first()
        if normalized and normalized.project:
            return list(normalized.project.images.order_by('-created_at'))
        return []

    @property
    def cover_image_url(self):
        images = self.images
        if images:
            return images[0].image_url or ''
        return ''

    @property
    def status_label(self):
        if self.event_date:
            today = timezone.now().date()
            if self.event_date < today:
                return 'Completed'
            return 'Planned'
        return 'Planned'

    @property
    def created_by(self):
        # Attempt to resolve the normalized Project.created_by_user via the
        # normalized Infrastructure/Non-Infrastructure mapping.
        infra = Non_Infrastructure_Project.objects.filter(non_infra_id=self.non_infra_id).select_related('project').first()
        return infra.project.created_by_user if infra and infra.project else None


 

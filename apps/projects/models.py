from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """Store additional user information including department"""
    DEPARTMENT_CHOICES = [
        ('engineer', 'Engineering Office'),
        ('mayor', "Mayor's Office"),
        ('admin', 'Administration'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    department = models.CharField(max_length=20, choices=DEPARTMENT_CHOICES, default='engineer')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_department_display()}"

    class Meta:
        ordering = ['user__username']


class InfrastructureProject(models.Model):
    """Infrastructure project model for tracking municipality projects"""

    LOCATION_CHOICES = [
        ('bagong_sikat', 'Bagong Sikat'),
        ('bagting', 'Bagting'),
        ('bantug', 'Bantug'),
        ('bitulok', 'Bitulok (North Poblacion)'),
        ('bugnan', 'Bugnan'),
        ('calabasa', 'Calabasa'),
        ('camachile', 'Camachile'),
        ('cuyapa', 'Cuyapa'),
        ('ligaya', 'Ligaya'),
        ('macasandal', 'Macasandal'),
        ('malinao', 'Malinao'),
        ('pantoc', 'Pantoc'),
        ('pinamalisan', 'Pinamalisan'),
        ('south_poblacion', 'South Poblacion'),
        ('sawmill', 'Sawmill'),
        ('tagumpay', 'Tagumpay'),
    ]

    PROJECT_CATEGORY_CHOICES = [
        ('road', 'Road & Bridge'),
        ('water', 'Water Supply'),
        ('sanitation', 'Sanitation'),
        ('health', 'Health Facility'),
        ('education', 'Education Facility'),
        ('energy', 'Energy'),
        ('ict', 'ICT/Telecommunications'),
        ('agriculture', 'Agriculture'),
        ('environment', 'Environment'),
        ('sports', 'Sports/Recreation'),
        ('other', 'Other'),
    ]

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

    PUBLICATION_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_review', 'Pending Review'),
        ('published', 'Published'),
        ('needs_revision', 'Needs Revision'),
        ('rejected', 'Rejected'),
    ]

    # Basic Information
    title = models.CharField(max_length=255)
    location = models.CharField(max_length=50, choices=LOCATION_CHOICES, help_text="Select barangay location")
    implementing_office = models.CharField(max_length=255, help_text="Office/Agency responsible for implementation")
    category = models.CharField(max_length=50, choices=PROJECT_CATEGORY_CHOICES)

    # Contractor & Procurement
    contractor = models.CharField(max_length=255, blank=True, help_text="Company name")
    procurement_method = models.CharField(max_length=50, choices=PROCUREMENT_METHOD_CHOICES)

    # Procurement Dates
    posting_date = models.DateField(null=True, blank=True, verbose_name="Posting Date")
    prebid_date = models.DateField(null=True, blank=True, verbose_name="Pre-bid Conference Date")
    bidding_date = models.DateField(null=True, blank=True, verbose_name="Bidding Date")
    noa_date = models.DateField(null=True, blank=True, verbose_name="Notice of Award (NOA) Date")
    ntp_date = models.DateField(null=True, blank=True, verbose_name="Notice to Proceed (NTP) Date")

    # Financial Information
    award_status = models.CharField(max_length=50, choices=AWARD_STATUS_CHOICES, default='ongoing_bidding')
    source_of_fund = models.CharField(max_length=255, blank=True, help_text="e.g., 20% Development Fund")
    abc_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Approved Budget for Contract (ABC)")
    contract_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Contract Price / Bid Amount")

    # Contract Adjustments
    variation_orders = models.TextField(blank=True, help_text="Record of variation orders with amounts, reasons, and approval dates")

    # Disbursements
    disbursements_to_date = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Total Disbursements/Payments to Date")
    disbursement_details = models.TextField(blank=True, help_text="Breakdown by milestone or payment schedule")

    # Schedule
    planned_start_date = models.DateField(null=True, blank=True)
    planned_end_date = models.DateField(null=True, blank=True)
    actual_start_date = models.DateField(null=True, blank=True)
    revised_completion_date = models.DateField(null=True, blank=True, help_text="If there's extension of time")

    # Progress Tracking
    cost_progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Cost Progress (%)")
    physical_progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Physical Progress (%)")

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='projects_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='projects_updated')

    # Publication & Approval
    publication_status = models.CharField(max_length=50, choices=PUBLICATION_STATUS_CHOICES, default='draft', help_text="Current publication/approval status")
    review_comments = models.TextField(blank=True, help_text="Admin comments for revision requests or rejections")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='projects_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True, help_text="When the project was reviewed by admin")

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Infrastructure Project'
        verbose_name_plural = 'Infrastructure Projects'

    def __str__(self):
        return f"{self.title} - {self.location}"

from django.db import models
from django.contrib.auth.models import User


class NonInfrastructureProject(models.Model):
    """Non-infrastructure project model for tracking municipality projects"""

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

    PUBLICATION_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_review', 'Pending Review'),
        ('published', 'Published'),
        ('needs_revision', 'Needs Revision'),
        ('rejected', 'Rejected'),
    ]

    # Basic Information
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="Project description and objectives")
    location = models.CharField(max_length=50, choices=LOCATION_CHOICES, help_text="Select barangay location")
    implementing_office = models.CharField(max_length=255, help_text="Office/Agency responsible for implementation")
    category = models.CharField(max_length=50, choices=PROJECT_CATEGORY_CHOICES)

    # Funding & Timeline
    source_of_fund = models.CharField(max_length=255, blank=True, help_text="e.g., GAA, PRDP")
    planned_start_date = models.DateField(null=True, blank=True)
    planned_end_date = models.DateField(null=True, blank=True)
    actual_start_date = models.DateField(null=True, blank=True)
    revised_completion_date = models.DateField(null=True, blank=True, help_text="If there's extension of time")

    # Progress Tracking - Single overall progress field
    overall_progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Overall Progress (%)")

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='non_infrastructure_projects_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='non_infrastructure_projects_updated')

    # Publication & Approval
    publication_status = models.CharField(max_length=50, choices=PUBLICATION_STATUS_CHOICES, default='draft', help_text="Current publication/approval status")
    review_comments = models.TextField(blank=True, help_text="Admin comments for revision requests or rejections")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='non_infrastructure_projects_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True, help_text="When the project was reviewed by admin")

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Non-Infrastructure Project'
        verbose_name_plural = 'Non-Infrastructure Projects'

    def __str__(self):
        return f"{self.title} - {self.location}"

from django.db import models
from django.contrib.auth.models import User


class Project(models.Model):
    """Model for infrastructure projects by the Engineering Office"""

    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('cancelled', 'Cancelled'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')

    # Project details
    location = models.CharField(max_length=255)
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    # Relationships
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_projects')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_projects')

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

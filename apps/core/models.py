from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """
    Store additional user information including department.
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
        default='engineer'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_department_display()}"

    class Meta:
        ordering = ['user__username']


class PasswordChangeHistory(models.Model):
    """
    Track all password changes for audit and security purposes.
    """
    CHANGE_METHOD_CHOICES = [
        ('creation', 'User Creation'),
        ('reset_link', 'Password Reset Link'),
        ('admin_edit', 'Admin Edit'),
        ('user_edit', 'User Self-Edit'),
        ('signal', 'System Change'),
    ]

    # The user whose password was changed
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='password_changes'
    )

    # When the password was changed
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Who initiated the password change (admin, user, or system)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='password_changes_made'
    )

    # How the password was changed
    method = models.CharField(
        max_length=20,
        choices=CHANGE_METHOD_CHOICES,
        default='signal'
    )

    # Optional notes (e.g., reason for admin reset)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-changed_at']
        verbose_name_plural = 'Password Change History'
        indexes = [
            models.Index(fields=['-changed_at']),
            models.Index(fields=['user', '-changed_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_method_display()} - {self.changed_at.strftime('%Y-%m-%d %H:%M')}"

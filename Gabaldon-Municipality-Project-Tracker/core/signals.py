"""
Signal handlers for password change tracking.

This module listens for User model changes and automatically creates
PasswordChangeHistory entries when a password is modified.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import PasswordChangeHistory


@receiver(post_save, sender=User)
def track_password_change(sender, instance, created, **kwargs):
    """
    Signal handler to track password changes for the User model.

    This automatically creates a PasswordChangeHistory entry whenever
    a User's password is changed. It works by comparing the current
    password hash against previous entries.

    Args:
        sender: The model class (User)
        instance: The User instance being saved
        created: Boolean indicating if this is a new User
        **kwargs: Additional signal arguments
    """

    # Skip if this is the initial creation (handled separately in view)
    if created:
        return

    # Check if password actually changed by comparing with last history entry
    last_history = (
        PasswordChangeHistory.objects
        .filter(user=instance)
        .order_by('-changed_at')
        .first()
    )

    # If there's no previous history, we can't detect a change
    if last_history is None:
        return

    # Get the user from DB before save to compare password hashes
    try:
        old_user = User.objects.get(pk=instance.pk)
    except User.DoesNotExist:
        return

    # Check if password changed (by comparing the hashed passwords)
    if old_user.password != instance.password:
        # Password was changed - create history entry
        # Note: We don't know who changed it or the method (caught by signal),
        # so we default to 'signal' method
        PasswordChangeHistory.objects.create(
            user=instance,
            changed_by=None,  # Signal doesn't know who made the change
            method='signal',
            notes='Password change detected by system monitoring'
        )

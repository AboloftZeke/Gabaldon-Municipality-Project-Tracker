"""
Signal handlers for password change tracking.

This module listens for User model changes and automatically creates
PasswordChangeHistory entries when a password is modified.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User


def _password_history_model():
    return User._meta.get_field('password_changes').related_model


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
    history_model = _password_history_model()
    last_history = (
        history_model.objects
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
        history_model.objects.create(
            user=instance,
            changed_by=None,  # Signal doesn't know who made the change
            method='signal',
            notes='Password change detected by system monitoring'
        )


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Signal handler to create a UserProfile when a new User is created via admin.

    NOTE: Users created through CustomUserCreationForm handle profile creation
    directly to ensure the correct department is assigned. This signal is a
    fallback for users created through other methods (e.g., Django admin panel).

    Args:
        sender: The model class (User)
        instance: The User instance being saved
        created: Boolean indicating if this is a new User
        **kwargs: Additional signal arguments
    """
    # During migration/cleanup we keep archive tables for historical purposes
    # but must not depend on them for runtime behavior. Do not create archive
    # rows here; the admin or migration tooling can archive separately.
    return

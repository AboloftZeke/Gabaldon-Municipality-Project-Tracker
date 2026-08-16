from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class CustomUserCreationForm(forms.ModelForm):
    """
    Form for creating new users.
    Passwords are generated later as temporary passwords.
    """
    ROLE_ADMIN = 'admin'
    ROLE_ENGINEERING = 'engineering'
    ROLE_MAYORS = 'mayors'
    ROLE_CHOICES = (
        ('', 'Select Department'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_ENGINEERING, 'Engineering Office'),
        (ROLE_MAYORS, "Mayor's Office"),
    )

    role = forms.ChoiceField(label='Department', choices=ROLE_CHOICES, initial='')

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Email is already in use.')
        return email

    def clean_role(self):
        role = self.cleaned_data.get('role', '')
        if not role:
            raise forms.ValidationError('Please select a department.')
        return role

    def save(self, commit=True, temporary_password=None):
        user = super().save(commit=False)
        role = self.cleaned_data['role']

        if not temporary_password:
            raise ValueError('temporary_password is required when creating a user.')

        user.set_password(temporary_password)

        # Treat all module-access roles as Django staff so mayor's office users
        # can log in like the other restricted access roles.
        user.is_staff = role in (self.ROLE_ADMIN, self.ROLE_ENGINEERING, self.ROLE_MAYORS)
        user.is_superuser = role == self.ROLE_ADMIN

        if commit:
            user.save()
            # Save the user profile with the department
            self._save_user_profile(user, role)

        return user

    def _save_user_profile(self, user, role):
        """Helper method to save the runtime department for access checks."""
        from apps.system.models import UserFlag

        department_map = {
            self.ROLE_ADMIN: 'admin',
            self.ROLE_ENGINEERING: 'engineer',
            self.ROLE_MAYORS: 'mayor',
        }
        department = department_map[role]
        user.profile.department = department
        UserFlag.objects.update_or_create(
            user=user,
            defaults={'department': department, 'must_change_password': False},
        )


class CustomUserChangeForm(forms.ModelForm):
    """
    Form for editing existing users.
    Supports role updates for staff/admin users.
    """
    ROLE_ADMIN = 'admin'
    ROLE_ENGINEERING = 'engineering'
    ROLE_MAYORS = 'mayors'
    ROLE_CHOICES = (
        (ROLE_ADMIN, 'Admin'),
        (ROLE_ENGINEERING, 'Engineering Office'),
        (ROLE_MAYORS, "Mayor's Office"),
    )

    role = forms.ChoiceField(label='Department', choices=ROLE_CHOICES)

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial role based on the compatibility profile or superuser status.
        profile = getattr(self.instance, 'profile', None)
        if profile:
            department_reverse_map = {
                'admin': self.ROLE_ADMIN,
                'engineer': self.ROLE_ENGINEERING,
                'mayor': self.ROLE_MAYORS,
            }
            self.fields['role'].initial = department_reverse_map.get(
                profile.department,
                self.ROLE_ENGINEERING
            )
        else:
            self.fields['role'].initial = self.ROLE_ADMIN if self.instance.is_superuser else self.ROLE_ENGINEERING

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        queryset = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if email and queryset.exists():
            raise forms.ValidationError('Email is already in use.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data.get('role', self.ROLE_ENGINEERING)

        # Keep Mayor's Office accounts in the staff-access group so they can log
        # into the application like the other module-approved roles.
        user.is_staff = role in (self.ROLE_ADMIN, self.ROLE_ENGINEERING, self.ROLE_MAYORS)
        user.is_superuser = role == self.ROLE_ADMIN

        if commit:
            user.save()
            # Save the user profile with the department
            self._save_user_profile(user, role)

        return user

    def _save_user_profile(self, user, role):
        """Helper method to save the runtime department for access checks."""
        from apps.system.models import UserFlag

        department_map = {
            self.ROLE_ADMIN: 'admin',
            self.ROLE_ENGINEERING: 'engineer',
            self.ROLE_MAYORS: 'mayor',
        }
        department = department_map.get(role, 'engineer')
        user.profile.department = department
        UserFlag.objects.update_or_create(
            user=user,
            defaults={'department': department, 'must_change_password': False},
        )


class UserListFilterForm(forms.Form):
    """
    Form for filtering users in the list view.
    Placeholder implementation - to be expanded with filter options.
    """
    search = forms.CharField(
        label='Search Users',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Search by username or email'})
    )

class UserPasswordChangeForm(forms.Form):
    """
    Form for users to change their password.
    Used when an employee is required to replace their temporary password.
    """

    current_password = forms.CharField(
        label='Current Password',
        widget=forms.PasswordInput
    )

    new_password = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput
    )

    confirm_password = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        current_password = self.cleaned_data.get('current_password')

        if current_password and not self.user.check_password(current_password):
            raise forms.ValidationError('Current password is incorrect.')

        return current_password

    def clean_new_password(self):
        new_password = self.cleaned_data.get('new_password')

        if new_password:
            validate_password(new_password, self.user)

        return new_password

    def clean(self):
        cleaned_data = super().clean()

        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if (
            new_password
            and confirm_password
            and new_password != confirm_password
        ):
            raise forms.ValidationError(
                'New passwords do not match.'
            )

        return cleaned_data

    def save(self):
        self.user.set_password(
            self.cleaned_data['new_password']
        )
        self.user.save(update_fields=['password'])

        return self.user

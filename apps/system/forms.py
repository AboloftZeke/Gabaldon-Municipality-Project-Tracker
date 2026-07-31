from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class CustomUserCreationForm(forms.ModelForm):
    """
    Form for creating new users.
    Uses built-in password validators and simple role assignment.
    """
    ROLE_ADMIN = 'admin'
    ROLE_ENGINEERING = 'engineering'
    ROLE_MAYORS = 'mayors'
    ROLE_CHOICES = (
        (ROLE_ADMIN, 'Admin'),
        (ROLE_ENGINEERING, 'Engineering Office'),
        (ROLE_MAYORS, "Mayor's Office"),
    )

    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput)
    role = forms.ChoiceField(label='Department', choices=ROLE_CHOICES, initial=ROLE_ENGINEERING)

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Email is already in use.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Passwords do not match.')

        if password1:
            try:
                validate_password(password1)
            except ValidationError as error:
                self.add_error('password1', error)

        return cleaned_data

    def save(self, commit=True, temporary_password=None):
        user = super().save(commit=False)
        role = self.cleaned_data.get('role', self.ROLE_ENGINEERING)
        

        if temporary_password:
            user.set_password(temporary_password)
        else:
            user.set_password(self.cleaned_data['password1'])

        user.is_staff = True
        user.is_superuser = role == self.ROLE_ADMIN

        if commit:
            user.save()
            # Save the user profile with the department
            self._save_user_profile(user, role)

        return user

    def _save_user_profile(self, user, role):
        """Helper method to save user profile with department."""
        from .models import UserProfile
        department_map = {
            self.ROLE_ADMIN: 'admin',
            self.ROLE_ENGINEERING: 'engineer',
            self.ROLE_MAYORS: 'mayor',
        }
        
        # Map the form role to the model department
        department = department_map.get(role, 'engineer')
        
        profile, created = UserProfile.objects.update_or_create(
            user=user,
            defaults={'department': department}
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
        # Set initial role based on user profile or superuser status
        if hasattr(self.instance, 'profile') and self.instance.profile:
            department_reverse_map = {
                'admin': self.ROLE_ADMIN,
                'engineer': self.ROLE_ENGINEERING,
                'mayor': self.ROLE_MAYORS,
            }
            self.fields['role'].initial = department_reverse_map.get(
                self.instance.profile.department,
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

        user.is_staff = True
        user.is_superuser = role == self.ROLE_ADMIN

        if commit:
            user.save()
            # Save the user profile with the department
            self._save_user_profile(user, role)

        return user

    def _save_user_profile(self, user, role):
        """Helper method to save user profile with department."""
        from .models import UserProfile
        department_map = {
            self.ROLE_ADMIN: 'admin',
            self.ROLE_ENGINEERING: 'engineer',
            self.ROLE_MAYORS: 'mayor',
        }
        
        # Map the form role to the model department
        department = department_map.get(role, 'engineer')
        
        # Use update_or_create to ensure the correct department is set
        profile, created = UserProfile.objects.update_or_create(
            user=user,
            defaults={'department': department}
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

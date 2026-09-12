from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

ACCOUNT_ASSIGNMENTS = {
    'admin': ('admin', 'admin', 'Admin'),
    'engineering': ('engineer', 'staff', 'Engineering Staff'),
    'engineering_head': ('engineer', 'head', 'Engineering Head'),
    'mayors': ('mayor', 'staff', "Mayor's Office Staff"),
    'mayors_head': ('mayor', 'head', "Mayor's Office Head"),
}
ACCOUNT_ROLE_CHOICES = tuple((key, value[2]) for key, value in ACCOUNT_ASSIGNMENTS.items())


def account_assignment(user):
    """Read persisted role for account editing; retain legacy missing-flag fallback."""
    from .models import UserFlag

    if user.is_superuser:
        return 'admin'
    flag = UserFlag.objects.filter(user=user).first() if user.pk else None
    if flag:
        return next((key for key, pair in ACCOUNT_ASSIGNMENTS.items()
                     if pair[:2] == (flag.department, flag.role)), '')
    department = getattr(getattr(user, 'profile', None), 'department', None)
    return {'engineer': 'engineering', 'mayor': 'mayors', 'admin': 'admin'}.get(department, '')


def account_role_label(value):
    return ACCOUNT_ASSIGNMENTS[value][2] if value in ACCOUNT_ASSIGNMENTS else 'Unassigned'


def save_account_assignment(user, assignment):
    from .models import UserFlag

    department, role, _ = ACCOUNT_ASSIGNMENTS[assignment]
    UserFlag.objects.update_or_create(
        user=user, defaults={'department': department, 'role': role},
    )
    user.__dict__.pop('_compat_profile', None)
    user._state.fields_cache.pop('flags', None)


class CustomUserCreationForm(forms.ModelForm):
    """
    Form for creating users who will establish a password by email.
    """
    ROLE_ADMIN = 'admin'
    ROLE_ENGINEERING = 'engineering'
    ROLE_MAYORS = 'mayors'
    ROLE_CHOICES = (('', 'Select account role'),) + ACCOUNT_ROLE_CHOICES

    role = forms.ChoiceField(label='Account role', choices=ROLE_CHOICES, initial='')
    email = forms.EmailField(required=True)

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
            raise forms.ValidationError('Please select an account role.')
        return role

    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data['role']
        user.set_unusable_password()

        # Treat all module-access roles as Django staff so mayor's office users
        # can log in like the other restricted access roles.
        user.is_staff = role in ACCOUNT_ASSIGNMENTS
        user.is_superuser = role == self.ROLE_ADMIN

        if commit:
            user.save()
            # Save the user profile with the department
            self._save_user_profile(user, role)

        return user

    def _save_user_profile(self, user, role):
        """Persist the selected department and responsibility together."""
        save_account_assignment(user, role)


class CustomUserChangeForm(forms.ModelForm):
    """
    Form for editing existing users.
    Supports role updates for staff/admin users.
    """
    ROLE_ADMIN = 'admin'
    ROLE_ENGINEERING = 'engineering'
    ROLE_MAYORS = 'mayors'
    ROLE_CHOICES = ACCOUNT_ROLE_CHOICES

    role = forms.ChoiceField(label='Account role', choices=ROLE_CHOICES)

    # Preserve the user's current activation state through the edit/confirm
    # workflow without exposing activation as an editable field. Activation and
    # deactivation are handled by their dedicated views.
    is_active = forms.BooleanField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].initial = self.instance.is_active

        self.fields['role'].initial = account_assignment(self.instance)

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
        user.is_staff = role in ACCOUNT_ASSIGNMENTS
        user.is_superuser = role == self.ROLE_ADMIN

        if commit:
            user.save()
            # Save the user profile with the department
            self._save_user_profile(user, role)

        return user

    def _save_user_profile(self, user, role):
        """Persist the selected department and responsibility together."""
        save_account_assignment(user, role)


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
    Form for authenticated users to change their password.
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

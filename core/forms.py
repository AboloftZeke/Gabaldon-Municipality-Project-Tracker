from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import InfrastructureProject


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

    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data.get('role', self.ROLE_ENGINEERING)

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
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.department = department_map.get(role, 'engineer')
        profile.save()


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
        fields = ('username', 'email', 'first_name', 'last_name', 'is_active')

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
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.department = department_map.get(role, 'engineer')
        profile.save()


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


class InfrastructureProjectForm(forms.ModelForm):
    """
    Form for creating and editing infrastructure projects.
    """

    class Meta:
        model = InfrastructureProject
        fields = [
            'title',
            'location',
            'implementing_office',
            'category',
            'contractor',
            'procurement_method',
            'posting_date',
            'prebid_date',
            'bidding_date',
            'noa_date',
            'ntp_date',
            'award_status',
            'source_of_fund',
            'abc_amount',
            'contract_price',
            'variation_orders',
            'disbursements_to_date',
            'disbursement_details',
            'planned_start_date',
            'planned_end_date',
            'actual_start_date',
            'revised_completion_date',
            'cost_progress_percentage',
            'physical_progress_percentage',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Project Title'
            }),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'implementing_office': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Office/Agency'
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'contractor': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Company Name'
            }),
            'procurement_method': forms.Select(attrs={'class': 'form-select'}),
            'posting_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'prebid_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'bidding_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'noa_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'ntp_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'award_status': forms.Select(attrs={'class': 'form-select'}),
            'source_of_fund': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., 20% Development Fund'
            }),
            'abc_amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Amount'
            }),
            'contract_price': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Amount'
            }),
            'variation_orders': forms.Textarea(attrs={
                'class': 'form-textarea',
                'placeholder': 'Record variation orders with amounts, reasons, and dates',
                'rows': 3
            }),
            'disbursements_to_date': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Total Amount'
            }),
            'disbursement_details': forms.Textarea(attrs={
                'class': 'form-textarea',
                'placeholder': 'Breakdown by milestone or payment schedule',
                'rows': 3
            }),
            'planned_start_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'planned_end_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'actual_start_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'revised_completion_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'cost_progress_percentage': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Percentage (0-100)',
                'min': '0',
                'max': '100',
                'step': '0.01'
            }),
            'physical_progress_percentage': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Percentage (0-100)',
                'min': '0',
                'max': '100',
                'step': '0.01'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field not in ['category', 'procurement_method', 'award_status']:
                self.fields[field].required = False

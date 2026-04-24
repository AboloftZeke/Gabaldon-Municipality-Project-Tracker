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

    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data.get('role', self.ROLE_ENGINEERING)

        user.set_password(self.cleaned_data['password1'])
        user.is_staff = True
        user.is_superuser = role == self.ROLE_ADMIN

        if commit:
            user.save()

        return user


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

        return user


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

from django import forms
from django.contrib.auth.models import User


class CustomUserCreationForm(forms.ModelForm):
    """
    Form for creating new users.
    Placeholder implementation - to be expanded with password fields and validation.
    """
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Passwords do not match.')

        return cleaned_data


class CustomUserChangeForm(forms.ModelForm):
    """
    Form for editing existing users.
    Placeholder implementation - to be expanded with additional fields.
    """
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff')


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

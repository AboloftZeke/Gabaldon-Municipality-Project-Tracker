from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from .forms import CustomUserCreationForm
from .models import UserProfile


class UserDeactivateViewTests(TestCase):
    def test_current_user_deactivation_shows_warning(self):
        user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='password',
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )

        self.client.force_login(user)
        response = self.client.get(reverse('user_deactivate', args=[user.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_deactivate'])
        self.assertEqual(response.context['warning_message'], 'You cannot deactivate your own account.')


class SuperuserProfileTests(TestCase):
    def test_created_superuser_gets_admin_profile(self):
        user = User.objects.create_superuser(
            username='root',
            email='root@example.com',
            password='password123',
        )

        profile = UserProfile.objects.get(user=user)

        self.assertTrue(user.is_superuser)
        self.assertEqual(profile.department, 'admin')


class UserCreationFormTests(TestCase):
    def test_user_creation_form_defaults_to_no_department(self):
        form = CustomUserCreationForm()

        self.assertEqual(form.fields['role'].initial, '')

    def test_user_creation_form_does_not_require_manual_password(self):
        form = CustomUserCreationForm(
            data={
                'username': 'tempuser',
                'email': 'tempuser@example.com',
                'first_name': 'Temp',
                'last_name': 'User',
                'role': 'engineering',
            }
        )

        self.assertTrue(form.is_valid())

        user = form.save(commit=True, temporary_password='TempPass123!')

        self.assertTrue(user.check_password('TempPass123!'))
        self.assertEqual(user.profile.department, 'engineer')

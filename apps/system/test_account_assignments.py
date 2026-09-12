import re
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from .forms import (
    ACCOUNT_ASSIGNMENTS, CustomUserChangeForm, CustomUserCreationForm,
)
from .models import UserFlag
from .account_setup import AccountSetupDeliveryError


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AccountAssignmentTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            'assignment-admin', 'admin@example.com', 'password',
        )
        self.client.force_login(self.admin)

    def data(self, assignment, username='account'):
        return {
            'username': username, 'email': f'{username}@example.com',
            'first_name': 'Test', 'last_name': 'Account', 'role': assignment,
            'is_active': True,
        }

    def test_all_five_assignments_survive_creation_confirmation_and_setup(self):
        for assignment, (department, role, label) in ACCOUNT_ASSIGNMENTS.items():
            with self.subTest(assignment=assignment):
                username = f'new-{assignment}'
                response = self.client.post(reverse('user_create'), self.data(assignment, username))
                self.assertRedirects(response, reverse('user_create_confirm'))
                self.assertFalse(User.objects.filter(username=username).exists())
                self.assertEqual(self.client.session['user_create_form_data']['role'], assignment)
                confirmation = self.client.get(reverse('user_create_confirm'))
                self.assertContains(confirmation, escape(label))
                response = self.client.post(reverse('user_create_confirm'))
                self.assertRedirects(response, reverse('user_list'))
                user = User.objects.get(username=username)
                self.assertEqual((user.flags.department, user.flags.role), (department, role))
                self.assertTrue(user.is_active)
                self.assertTrue(user.is_staff)
                self.assertEqual(user.is_superuser, assignment == 'admin')
                self.assertFalse(user.has_usable_password())
                self.assertEqual(mail.outbox[-1].to, [user.email])
                self.assertIn('/account-setup/', mail.outbox[-1].body)

    def test_staff_head_edits_preserve_confirmation_labels_and_password(self):
        for staff, head in [('engineering', 'engineering_head'), ('mayors', 'mayors_head')]:
            form = CustomUserCreationForm(self.data(staff, staff))
            self.assertTrue(form.is_valid(), form.errors)
            user = form.save()
            user.set_password('existing-password')
            user.save()
            original_password = user.password
            for before, after in [(staff, head), (head, staff)]:
                with self.subTest(before=before, after=after):
                    edit_url = reverse('user_edit', args=[user.pk])
                    confirm_url = reverse('user_edit_confirm', args=[user.pk])
                    response = self.client.get(edit_url)
                    self.assertEqual(response.context['form']['role'].value(), before)
                    self.assertRedirects(self.client.post(edit_url, self.data(after, staff)), confirm_url)
                    saved = self.client.session[f'user_edit_form_data_{user.pk}']
                    self.assertEqual(saved['old_data']['role'], before)
                    self.assertEqual(saved['new_data']['role'], after)
                    # Returning to the form must also preserve the pending selection.
                    self.assertEqual(self.client.get(edit_url).context['form']['role'].value(), after)
                    response = self.client.get(confirm_url)
                    self.assertContains(response, escape(ACCOUNT_ASSIGNMENTS[before][2]))
                    self.assertContains(response, escape(ACCOUNT_ASSIGNMENTS[after][2]))
                    self.assertContains(response, 'CHANGED')
                    self.assertRedirects(self.client.post(confirm_url), reverse('user_list'))
                    user.refresh_from_db()
                    self.assertEqual((user.flags.department, user.flags.role), ACCOUNT_ASSIGNMENTS[after][:2])
                    self.assertEqual(user.password, original_password)
                    self.assertTrue(user.is_active)
                    self.assertTrue(user.is_staff)
                    self.assertFalse(user.is_superuser)

    def test_selector_only_accepts_valid_assignments(self):
        expected = {('admin', 'admin'), ('engineer', 'staff'), ('engineer', 'head'), ('mayor', 'staff'), ('mayor', 'head')}
        self.assertEqual({value[:2] for value in ACCOUNT_ASSIGNMENTS.values()}, expected)
        for invalid in ['admin_staff', 'admin_head', 'engineer_admin', 'mayor_admin', 'head', 'staff', '']:
            for form_type in [CustomUserCreationForm, CustomUserChangeForm]:
                with self.subTest(form=form_type.__name__, assignment=invalid):
                    form = form_type(self.data(invalid))
                    self.assertFalse(form.is_valid())
                    self.assertIn('role', form.errors)

    def test_tampered_confirmation_assignment_is_revalidated(self):
        session = self.client.session
        session['user_create_form_data'] = self.data('admin_head')
        session.save()
        self.client.post(reverse('user_create_confirm'))
        self.assertFalse(User.objects.filter(username='account').exists())

    def test_list_distinguishes_heads_and_staff_with_existing_department_filter(self):
        for assignment in ['engineering', 'engineering_head', 'mayors', 'mayors_head']:
            form = CustomUserCreationForm(self.data(assignment, assignment))
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
        response = self.client.get(reverse('user_list'))
        for assignment in ACCOUNT_ASSIGNMENTS:
            self.assertContains(response, escape(ACCOUNT_ASSIGNMENTS[assignment][2]))
        response = self.client.get(reverse('user_list'), {'department': 'engineer'})
        self.assertEqual({u.username for u in response.context['users']}, {'engineering', 'engineering_head'})

    def test_editing_inactive_head_does_not_activate_account(self):
        user = User.objects.create_user('inactive', email='inactive@example.com', is_active=False, is_staff=True)
        UserFlag.objects.create(user=user, department='engineer', role='head')
        data = self.data('engineering', 'inactive')
        data['is_active'] = False
        form = CustomUserChangeForm(data, instance=user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_non_admin_cannot_assign_accounts(self):
        user = User.objects.create_user('office-head', is_staff=True)
        UserFlag.objects.create(user=user, department='engineer', role='head')
        self.client.force_login(user)
        self.assertEqual(self.client.post(reverse('user_create'), self.data('admin')).status_code, 403)

    def test_head_can_complete_existing_setup_and_still_requires_otp(self):
        self.client.post(reverse('user_create'), self.data('engineering_head'))
        self.client.post(reverse('user_create_confirm'))
        path = re.search(r'http://testserver(/account-setup/[^\s]+)', mail.outbox[-1].body).group(1)
        self.client.logout()
        response = self.client.get(path)
        password = 'HeadSecurePass!2026'
        self.assertRedirects(self.client.post(response.url, {
            'new_password1': password, 'new_password2': password,
        }), reverse('account_setup_complete'))
        user = User.objects.get(username='account')
        self.assertTrue(user.check_password(password))
        self.assertEqual(user.flags.role, 'head')
        self.assertRedirects(self.client.post(reverse('login'), {
            'username': user.username, 'password': password,
        }), reverse('login_otp_verify'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_head_setup_delivery_failure_rolls_back_user_and_assignment(self):
        self.client.post(reverse('user_create'), self.data('mayors_head'))
        with patch('apps.system.views.send_account_setup_email', side_effect=AccountSetupDeliveryError):
            self.client.post(reverse('user_create_confirm'))
        self.assertFalse(User.objects.filter(username='account').exists())
        self.assertFalse(UserFlag.objects.filter(user__username='account').exists())
        self.assertEqual(self.client.session['user_create_form_data']['role'], 'mayors_head')

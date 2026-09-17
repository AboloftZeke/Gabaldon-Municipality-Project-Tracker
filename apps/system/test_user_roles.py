
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import UserRole
from .views import _department_for_user


class UserRoleRoleTests(TestCase):
    def user(self, name):
        return User.objects.create_user(name, email=f'{name}@example.com')

    def test_omitted_role_preserves_existing_department_mapping(self):
        for department, role in [('engineer', 'staff'), ('mayor', 'staff'), ('admin', 'admin'), ('', 'staff')]:
            with self.subTest(department=department):
                flag = UserRole.objects.create(user=self.user(f'user-{department}'), department=department)
                flag.refresh_from_db()
                self.assertEqual(flag.role, role)
                self.assertEqual(flag.department, department)

    def test_heads_are_valid_for_both_offices(self):
        for department in ['engineer', 'mayor']:
            flag = UserRole(user=self.user(department), department=department, role='head')
            flag.full_clean()
            flag.save()
            flag.refresh_from_db()
            self.assertEqual(flag.role, 'head')
            self.assertEqual(_department_for_user(flag.user), department)

    def test_invalid_combinations_fail_model_validation_and_save(self):
        user = self.user('invalid')
        for department, role in [('admin', 'head'), ('admin', 'staff'), ('engineer', 'admin'), ('mayor', 'admin'), ('', 'head'), ('unknown', 'staff'), ('engineer', 'unknown')]:
            with self.subTest(department=department, role=role):
                flag = UserRole(user=user, department=department, role=role)
                with self.assertRaises(ValidationError):
                    flag.full_clean()
                with self.assertRaises(ValidationError):
                    flag.save()

    def test_database_constraint_prevents_validation_bypass(self):
        flag = UserRole.objects.create(user=self.user('constraint'), department='engineer')
        for role in ['admin', '', 'unknown']:
            with self.subTest(role=role), self.assertRaises(IntegrityError), transaction.atomic():
                UserRole.objects.filter(pk=flag.pk).update(role=role)

    def test_existing_account_forms_work_without_role_field_changes(self):
        form = CustomUserCreationForm({
            'username': 'account', 'email': 'account@example.com',
            'first_name': '', 'last_name': '', 'role': 'engineering',
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertFalse(user.has_usable_password())
        for selected, department, role in [('admin', 'admin', 'admin'), ('mayors', 'mayor', 'staff'), ('engineering', 'engineer', 'staff')]:
            form = CustomUserChangeForm({
                'username': user.username, 'email': user.email,
                'first_name': '', 'last_name': '', 'role': selected,
                'is_active': True,
            }, instance=user)
            self.assertTrue(form.is_valid(), form.errors)
            user = form.save()
            flag = UserRole.objects.get(user=user)
            self.assertEqual((flag.department, flag.role), (department, role))
            self.assertTrue(user.is_staff)
            self.assertEqual(user.is_superuser, selected == 'admin')

    def test_unrelated_save_preserves_head_and_user_flags(self):
        user = self.user('head')
        user.is_staff = True
        user.save()
        flag = UserRole.objects.create(user=user, department='engineer', role='head')
        UserRole.objects.update_or_create(user=user, defaults={'department': 'engineer'})
        flag.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(flag.role, 'head')
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)

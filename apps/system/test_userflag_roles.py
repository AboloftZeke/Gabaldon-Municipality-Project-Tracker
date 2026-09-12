import importlib

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase, TransactionTestCase, override_settings

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import UserFlag
from .views import _department_for_user


class UserFlagRoleTests(TestCase):
    def user(self, name):
        return User.objects.create_user(name, email=f'{name}@example.com')

    def test_omitted_role_preserves_existing_department_mapping(self):
        for department, role in [('engineer', 'staff'), ('mayor', 'staff'), ('admin', 'admin'), ('', 'staff')]:
            with self.subTest(department=department):
                flag = UserFlag.objects.create(user=self.user(f'user-{department}'), department=department)
                flag.refresh_from_db()
                self.assertEqual(flag.role, role)
                self.assertEqual(flag.department, department)

    def test_heads_are_valid_for_both_offices(self):
        for department in ['engineer', 'mayor']:
            flag = UserFlag(user=self.user(department), department=department, role='head')
            flag.full_clean()
            flag.save()
            flag.refresh_from_db()
            self.assertEqual(flag.role, 'head')
            self.assertEqual(_department_for_user(flag.user), department)

    def test_invalid_combinations_fail_model_validation_and_save(self):
        user = self.user('invalid')
        for department, role in [('admin', 'head'), ('admin', 'staff'), ('engineer', 'admin'), ('mayor', 'admin'), ('', 'head'), ('unknown', 'staff'), ('engineer', 'unknown')]:
            with self.subTest(department=department, role=role):
                flag = UserFlag(user=user, department=department, role=role)
                with self.assertRaises(ValidationError):
                    flag.full_clean()
                with self.assertRaises(ValidationError):
                    flag.save()

    def test_database_constraint_prevents_validation_bypass(self):
        flag = UserFlag.objects.create(user=self.user('constraint'), department='engineer')
        for role in ['admin', '', 'unknown']:
            with self.subTest(role=role), self.assertRaises(IntegrityError), transaction.atomic():
                UserFlag.objects.filter(pk=flag.pk).update(role=role)

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
            flag = UserFlag.objects.get(user=user)
            self.assertEqual((flag.department, flag.role), (department, role))
            self.assertTrue(user.is_staff)
            self.assertEqual(user.is_superuser, selected == 'admin')

    def test_unrelated_save_preserves_head_and_user_flags(self):
        user = self.user('head')
        user.is_staff = True
        user.save()
        flag = UserFlag.objects.create(user=user, department='engineer', role='head')
        UserFlag.objects.update_or_create(user=user, defaults={'department': 'engineer'})
        flag.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(flag.role, 'head')
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)


@override_settings(MIGRATION_MODULES={})
class UserFlagRoleMigrationTests(TransactionTestCase):
    """Execute 0031 on an isolated historical table, not legacy PostgreSQL SQL."""

    def setUp(self):
        loader = MigrationLoader(None)
        self.state = loader.project_state([('system', '0030_remove_must_change_password')])
        self.state.models['system', 'userflag'].options['db_table'] = 'phase2_userflag_migration'
        self.legacy = self.state.apps.get_model('system', 'UserFlag')
        with connection.schema_editor() as editor:
            editor.create_model(self.legacy)
        self.migration = importlib.import_module('apps.system.migrations.0031_userflag_role')

    def tearDown(self):
        with connection.schema_editor() as editor:
            editor.delete_model(self.state.apps.get_model('system', 'UserFlag'))

    def apply_operation(self, operation):
        previous = self.state
        following = previous.clone()
        operation.state_forwards('system', following)
        with connection.schema_editor() as editor:
            operation.database_forwards('system', editor, previous, following)
        self.state = following

    def test_migration_backfills_existing_rows_without_changing_users(self):
        for department in ['engineer', 'mayor', 'admin', '']:
            user = User.objects.create_user(f'legacy-{department}', password='unchanged', is_staff=True)
            self.legacy.objects.create(user_id=user.pk, department=department)
        unflagged = User.objects.create_user('unflagged', is_staff=True)
        before = list(User.objects.order_by('pk').values('pk', 'password', 'is_staff', 'is_superuser'))
        for operation in self.migration.Migration.operations:
            self.apply_operation(operation)
        Flag = self.state.apps.get_model('system', 'UserFlag')
        self.assertEqual(dict(Flag.objects.values_list('department', 'role')), {
            'engineer': 'staff', 'mayor': 'staff', 'admin': 'admin', '': 'staff',
        })
        self.assertFalse(Flag.objects.filter(user_id=unflagged.pk).exists())
        self.assertEqual(before, list(User.objects.order_by('pk').values('pk', 'password', 'is_staff', 'is_superuser')))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Flag.objects.filter(department='engineer').update(role='admin')

    def test_unknown_department_stops_backfill_without_reclassification(self):
        user = User.objects.create_user('unknown-department')
        self.legacy.objects.create(user_id=user.pk, department='unexpected')
        self.apply_operation(self.migration.Migration.operations[0])
        with self.assertRaisesMessage(RuntimeError, 'unknown departments'):
            self.apply_operation(self.migration.Migration.operations[1])
        Flag = self.state.apps.get_model('system', 'UserFlag')
        self.assertEqual(Flag.objects.get().department, 'unexpected')

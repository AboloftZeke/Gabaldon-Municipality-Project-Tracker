"""Upgrade paths from both the simplified and earlier enhancement branches."""

from django.db import connection, models
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase


class SponsorMigrationTests(TransactionTestCase):
    base = [('system', '0012_remove_not_yet_started_infrastructure_status')]
    target = [('system', '0013_noninfrastructure_sponsored_by')]
    legacy = '0011_noninfrastructure_sponsored_by'

    def setUp(self):
        executor = MigrationExecutor(connection)
        self.latest = executor.loader.graph.leaf_nodes()
        self.bad_column = False
        self.recorder = MigrationRecorder(connection)
        self.new_model = executor.loader.project_state(self.target).apps.get_model(
            'system', 'NonInfrastructureProject',
        )
        self.addCleanup(self.restore_schema)
        executor.migrate(self.base)
        apps = executor.loader.project_state(self.base).apps
        self.old_model = apps.get_model('system', 'NonInfrastructureProject')
        project = apps.get_model('system', 'Project').objects.create(
            project_type='non_infrastructure',
        )
        self.record = self.old_model.objects.create(
            project=project, title='Existing activity',
            target_beneficiaries='Existing beneficiary group',
        )

    def restore_schema(self):
        self.recorder.record_unapplied('system', self.legacy)
        if self.bad_column:
            with connection.schema_editor() as editor:
                editor.remove_field(self.new_model, self.new_model._meta.get_field('sponsored_by'))
        MigrationExecutor(connection).migrate(self.latest)

    def columns(self):
        with connection.cursor() as cursor:
            return [column.name for column in connection.introspection.get_table_description(
                cursor, self.new_model._meta.db_table,
            )]

    def create_existing_column(self, *, legacy_record=True):
        # Reproduce the physical column and migration history from the former
        # main-based branch, without importing its removed migration file.
        with connection.schema_editor() as editor:
            editor.add_field(self.new_model, self.new_model._meta.get_field('sponsored_by'))
        self.new_model.objects.filter(pk=self.record.pk).update(sponsored_by='Gabaldon Sponsors — Añonuevo')
        if legacy_record:
            self.recorder.record_applied('system', self.legacy)

    def assert_data_preserved(self, expected):
        record = self.new_model.objects.get(pk=self.record.pk)
        self.assertEqual(record.sponsored_by, expected)
        self.assertEqual(record.target_beneficiaries, 'Existing beneficiary group')
        self.assertEqual(record.title, 'Existing activity')
        self.assertEqual(self.columns().count('sponsored_by'), 1)

    def test_fresh_upgrade_creates_column_and_keeps_existing_record(self):
        self.assertNotIn('sponsored_by', self.columns())
        MigrationExecutor(connection).migrate(self.target)
        self.assert_data_preserved('')
        self.assertTrue(self.recorder.migration_qs.filter(app='system', name=self.target[0][1]).exists())

    def test_legacy_upgrade_keeps_existing_column_values_and_history(self):
        self.create_existing_column()
        MigrationExecutor(connection).migrate(self.target)
        self.assert_data_preserved('Gabaldon Sponsors — Añonuevo')
        self.assertTrue(self.recorder.migration_qs.filter(app='system', name=self.legacy).exists())
        self.assertTrue(self.recorder.migration_qs.filter(app='system', name=self.target[0][1]).exists())

    def test_existing_compatible_column_without_legacy_record_is_adopted(self):
        self.create_existing_column(legacy_record=False)
        MigrationExecutor(connection).migrate(self.target)
        self.assert_data_preserved('Gabaldon Sponsors — Añonuevo')
        self.assertFalse(self.recorder.migration_qs.filter(app='system', name=self.legacy).exists())

    def test_legacy_rollback_and_reapply_preserve_earlier_column(self):
        self.create_existing_column()
        MigrationExecutor(connection).migrate(self.target)
        MigrationExecutor(connection).migrate(self.base)
        self.assert_data_preserved('Gabaldon Sponsors — Añonuevo')
        MigrationExecutor(connection).migrate(self.target)
        self.assert_data_preserved('Gabaldon Sponsors — Añonuevo')

    def test_fresh_rollback_removes_its_own_column_and_can_be_reapplied(self):
        MigrationExecutor(connection).migrate(self.target)
        MigrationExecutor(connection).migrate(self.base)
        self.assertNotIn('sponsored_by', self.columns())
        self.assertTrue(self.old_model.objects.filter(pk=self.record.pk).exists())
        MigrationExecutor(connection).migrate(self.target)
        self.assert_data_preserved('')

    def test_incompatible_existing_column_is_rejected_without_rewriting_data(self):
        field = models.IntegerField(null=True)
        field.set_attributes_from_name('sponsored_by')
        with connection.schema_editor() as editor:
            editor.add_field(self.old_model, field)
        self.bad_column = True
        with self.assertRaisesMessage(RuntimeError, 'does not match the expected'):
            MigrationExecutor(connection).migrate(self.target)
        self.assertFalse(self.recorder.migration_qs.filter(app='system', name=self.target[0][1]).exists())
        self.assertEqual(self.old_model.objects.get(pk=self.record.pk).target_beneficiaries, 'Existing beneficiary group')

    def test_repeated_migrate_does_not_duplicate_column_or_lose_values(self):
        self.create_existing_column()
        MigrationExecutor(connection).migrate(self.target)
        MigrationExecutor(connection).migrate(self.target)
        self.assert_data_preserved('Gabaldon Sponsors — Añonuevo')

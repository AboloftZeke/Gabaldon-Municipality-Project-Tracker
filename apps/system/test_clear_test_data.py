from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.test import TestCase

from apps.system.management.commands.clear_test_data import Command
from apps.system.models import (
    InfrastructureProgressUpdate,
    InfrastructureProject,
    InspectionEvidence,
    NonInfrastructureCategory,
    NonInfrastructureEvidence,
    NonInfrastructureProgressUpdate,
    NonInfrastructureProject,
    Project,
    ProjectImage,
    ProjectInspection,
    ProjectReport,
    ProjectRevision,
    UserRole,
)
from apps.system.publication_workflow import PublicationStatus


class ClearTestDataCommandTests(TestCase):
    def setUp(self):
        self.required_user = User.objects.create_superuser(
            username='developer-admin',
            email='developer@example.com',
            password='testpass123',
        )
        self.seed_user = User.objects.create_user(username='seed_projects_engineer')
        self.seed_head = User.objects.create_user(username='seed_projects_mayor_head')
        UserRole.objects.create(
            user=self.seed_user,
            department='engineer',
            role='staff',
        )
        self.category = NonInfrastructureCategory.objects.create(
            type_code='cleanup-test-category',
            type_name='Cleanup Test Category',
        )

        self.infrastructure_base = Project.objects.create(project_type='infrastructure')
        self.infrastructure = InfrastructureProject.objects.create(
            project=self.infrastructure_base,
            infrastructure_code='SEED-INF-000001',
            title='Test Infrastructure Project',
        )
        self.inspection = ProjectInspection.objects.create(
            project=self.infrastructure_base,
            inspection_date='2026-10-01',
            completion_percentage=25,
        )
        InspectionEvidence.objects.create(
            inspection=self.inspection,
            evidence_type='image',
            original_name='inspection.jpg',
            storage_name='inspections/inspection.jpg',
            file_url='/media/inspections/inspection.jpg',
            content_type='image/jpeg',
            uploaded_by_user=self.seed_user,
        )
        infrastructure_update = InfrastructureProgressUpdate.objects.create(
            infrastructure=self.infrastructure,
            previous_official_status='not_yet_started',
            new_official_status='ongoing',
            updated_by=self.seed_user,
        )
        infrastructure_update.supporting_inspections.add(self.inspection)
        ProjectImage.objects.create(
            project=self.infrastructure_base,
            image_url='/media/projects/infrastructure.jpg',
        )
        ProjectReport.objects.create(
            project=self.infrastructure_base,
            report_name='Infrastructure test report',
        )

        self.non_infrastructure_base = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=self.seed_user,
        )
        self.non_infrastructure = NonInfrastructureProject.objects.create(
            project=self.non_infrastructure_base,
            title='Test Non-Infrastructure Project',
            category=self.category,
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
        )
        self.manual_non_infrastructure = NonInfrastructureProject.objects.create(
            project=Project.objects.create(
                project_type='non_infrastructure',
                created_by_user=self.required_user,
            ),
            title='Manual Non-Infrastructure Test Project',
            category=self.category,
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
        )
        self.update = NonInfrastructureProgressUpdate.objects.create(
            non_infrastructure=self.non_infrastructure,
            previous_status='planned',
            proposed_status='ongoing',
            submitted_by=self.seed_user,
            review_status=NonInfrastructureProgressUpdate.ReviewStatus.APPROVED,
        )
        NonInfrastructureEvidence.objects.create(
            progress_update=self.update,
            evidence_file=SimpleUploadedFile(
                'evidence.pdf', b'%PDF-1.4 test', content_type='application/pdf',
            ),
            uploaded_by=self.seed_user,
        )
        self.revision = ProjectRevision.objects.create(
            project=self.non_infrastructure_base,
            revision_number=1,
            status=PublicationStatus.APPROVED,
            submitted_by=self.seed_user,
        )
        self.update.publication_revision = self.revision
        self.update.save(update_fields=['publication_revision'])

        self.unrelated_project = Project.objects.create(project_type='other')
        self.unrelated_infrastructure = InfrastructureProject.objects.create(
            project=Project.objects.create(
                project_type='infrastructure',
                created_by_user=self.required_user,
            ),
            infrastructure_code='LOCAL-INF-000001',
            title='Required Infrastructure Record',
        )
        self.unrelated_non_infrastructure = NonInfrastructureProject.objects.create(
            project=Project.objects.create(
                project_type='non_infrastructure',
                created_by_user=self.required_user,
            ),
            title='Required Non-Infrastructure Record',
            project_type=NonInfrastructureProject.ProjectType.PROGRAM,
        )

    def test_scope_is_required_and_scopes_are_mutually_exclusive(self):
        with self.assertRaisesMessage(CommandError, 'Please specify one cleanup scope'):
            call_command('clear_test_data')
        with self.assertRaisesMessage(CommandError, 'mutually exclusive'):
            call_command('clear_test_data', '--infra', '--non-infra')

    def test_each_scope_without_confirm_is_a_dry_run(self):
        for option in ('--infra', '--non-infra', '--users', '--all'):
            with self.subTest(option=option):
                output = StringIO()
                call_command('clear_test_data', option, stdout=output)
                self.assertIn('DRY RUN: No data was deleted.', output.getvalue())
                self.assertTrue(InfrastructureProject.objects.filter(pk=self.infrastructure.pk).exists())
                self.assertTrue(NonInfrastructureProject.objects.filter(pk=self.non_infrastructure.pk).exists())
                self.assertTrue(User.objects.filter(pk=self.seed_user.pk).exists())

    def test_infra_scope_isolated_from_non_infrastructure_and_users(self):
        output = StringIO()
        call_command('clear_test_data', '--infra', '--confirm', stdout=output)

        self.assertIn('Scope: Infrastructure', output.getvalue())
        self.assertFalse(InfrastructureProject.objects.filter(pk=self.infrastructure.pk).exists())
        self.assertFalse(Project.objects.filter(pk=self.infrastructure_base.pk).exists())
        self.assertFalse(InfrastructureProgressUpdate.objects.exists())
        self.assertFalse(InspectionEvidence.objects.exists())
        self.assertTrue(NonInfrastructureProject.objects.filter(pk=self.non_infrastructure.pk).exists())
        self.assertTrue(
            NonInfrastructureProject.objects.filter(pk=self.manual_non_infrastructure.pk).exists()
        )
        self.assertTrue(Project.objects.filter(pk=self.non_infrastructure_base.pk).exists())
        self.assertTrue(NonInfrastructureEvidence.objects.exists())
        self.assertTrue(User.objects.filter(pk=self.seed_user.pk).exists())

    def test_non_infra_scope_isolated_from_infrastructure_and_users(self):
        output = StringIO()
        call_command('clear_test_data', '--non-infra', '--confirm', stdout=output)

        self.assertIn('Scope: Non-Infrastructure', output.getvalue())
        self.assertFalse(NonInfrastructureProject.objects.filter(pk=self.non_infrastructure.pk).exists())
        self.assertFalse(
            NonInfrastructureProject.objects.filter(pk=self.manual_non_infrastructure.pk).exists()
        )
        self.assertFalse(Project.objects.filter(pk=self.non_infrastructure_base.pk).exists())
        self.assertFalse(NonInfrastructureProgressUpdate.objects.exists())
        self.assertFalse(NonInfrastructureEvidence.objects.exists())
        self.assertTrue(InfrastructureProject.objects.filter(pk=self.infrastructure.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.infrastructure_base.pk).exists())
        self.assertTrue(InfrastructureProgressUpdate.objects.exists())
        self.assertTrue(User.objects.filter(pk=self.seed_user.pk).exists())

    def test_users_scope_only_removes_recognized_seed_users(self):
        call_command('clear_test_data', '--users', '--confirm', stdout=StringIO())

        self.assertFalse(User.objects.filter(pk=self.seed_user.pk).exists())
        self.assertFalse(User.objects.filter(pk=self.seed_head.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.required_user.pk).exists())
        self.assertTrue(InfrastructureProject.objects.filter(pk=self.infrastructure.pk).exists())
        self.assertTrue(NonInfrastructureProject.objects.filter(pk=self.non_infrastructure.pk).exists())
        self.assertTrue(
            NonInfrastructureProject.objects.filter(pk=self.manual_non_infrastructure.pk).exists()
        )

    def test_all_scope_removes_projects_and_seed_users(self):
        output = StringIO()
        call_command('clear_test_data', '--all', '--confirm', stdout=output)

        self.assertIn('Scope: All', output.getvalue())
        self.assertFalse(InfrastructureProject.objects.filter(pk=self.infrastructure.pk).exists())
        self.assertFalse(NonInfrastructureProject.objects.filter(pk=self.non_infrastructure.pk).exists())
        self.assertFalse(
            NonInfrastructureProject.objects.filter(pk=self.manual_non_infrastructure.pk).exists()
        )
        self.assertFalse(ProjectRevision.objects.filter(pk=self.revision.pk).exists())
        self.assertFalse(User.objects.filter(pk=self.seed_user.pk).exists())
        self.assertFalse(User.objects.filter(pk=self.seed_head.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.required_user.pk).exists())
        self.assertTrue(NonInfrastructureCategory.objects.filter(pk=self.category.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.unrelated_project.pk).exists())

    def test_unexpected_failure_rolls_back_deletions(self):
        def delete_then_fail(scope_name, scope):
            ProjectRevision.objects.filter(
                project_id__in=scope['project_ids'],
            ).delete()
            raise RuntimeError('simulated cleanup failure')

        with patch.object(Command, '_delete_scope', side_effect=delete_then_fail):
            with self.assertRaises(CommandError):
                call_command('clear_test_data', '--non-infra', '--confirm', stdout=StringIO())

        self.assertTrue(ProjectRevision.objects.filter(pk=self.revision.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.non_infrastructure_base.pk).exists())
        self.assertTrue(NonInfrastructureEvidence.objects.exists())

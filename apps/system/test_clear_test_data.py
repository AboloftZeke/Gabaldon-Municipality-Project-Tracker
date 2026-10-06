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

    def test_without_confirm_is_a_dry_run(self):
        output = StringIO()
        call_command('clear_test_data', stdout=output)

        self.assertIn('DRY RUN: No data was deleted.', output.getvalue())
        self.assertTrue(InfrastructureProject.objects.filter(pk=self.infrastructure.pk).exists())
        self.assertTrue(NonInfrastructureProject.objects.filter(pk=self.non_infrastructure.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.unrelated_project.pk).exists())
        self.assertTrue(InfrastructureProject.objects.filter(pk=self.unrelated_infrastructure.pk).exists())
        self.assertTrue(
            NonInfrastructureProject.objects.filter(pk=self.unrelated_non_infrastructure.pk).exists()
        )
        self.assertTrue(User.objects.filter(pk=self.required_user.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.seed_user.pk).exists())

    def test_confirm_removes_scoped_records_and_preserves_configuration(self):
        output = StringIO()
        call_command('clear_test_data', '--confirm', stdout=output)

        self.assertIn('Test data cleanup completed successfully.', output.getvalue())
        self.assertFalse(InfrastructureProject.objects.filter(pk=self.infrastructure.pk).exists())
        self.assertFalse(NonInfrastructureProject.objects.filter(pk=self.non_infrastructure.pk).exists())
        self.assertFalse(Project.objects.filter(pk=self.infrastructure_base.pk).exists())
        self.assertFalse(Project.objects.filter(pk=self.non_infrastructure_base.pk).exists())
        self.assertFalse(ProjectRevision.objects.filter(pk=self.revision.pk).exists())
        self.assertFalse(InfrastructureProgressUpdate.objects.exists())
        self.assertFalse(NonInfrastructureProgressUpdate.objects.exists())
        self.assertFalse(InspectionEvidence.objects.exists())
        self.assertFalse(NonInfrastructureEvidence.objects.exists())
        self.assertTrue(Project.objects.filter(pk=self.unrelated_project.pk).exists())
        self.assertTrue(NonInfrastructureCategory.objects.filter(pk=self.category.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.required_user.pk).exists())
        self.assertFalse(User.objects.filter(pk=self.seed_user.pk).exists())

    def test_unexpected_failure_rolls_back_deletions(self):
        def delete_then_fail(scope):
            ProjectRevision.objects.filter(
                project_id__in=scope['project_ids'],
            ).delete()
            raise RuntimeError('simulated cleanup failure')

        with patch.object(Command, '_delete_scoped_data', side_effect=delete_then_fail):
            with self.assertRaises(CommandError):
                call_command('clear_test_data', '--confirm', stdout=StringIO())

        self.assertTrue(ProjectRevision.objects.filter(pk=self.revision.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.non_infrastructure_base.pk).exists())
        self.assertTrue(NonInfrastructureEvidence.objects.exists())

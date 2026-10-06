from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.deletion import ProtectedError

from apps.system.models import (
    FinancialRecord,
    InfrastructureProgressUpdate,
    InfrastructureProject,
    InfrastructureSchedule,
    InspectionEvidence,
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


SEED_USER_PREFIX = 'seed_projects_'
SEED_INFRASTRUCTURE_CODE_PREFIX = 'SEED-INF-'


class Command(BaseCommand):
    help = 'Safely remove local test project data without changing the database schema.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Permanently delete the scoped test data. Without this flag, run a dry run.',
        )

    def handle(self, *args, **options):
        scope = self._scope()
        counts = self._counts(scope)

        if not options['confirm']:
            self.stdout.write(self.style.WARNING('DRY RUN: No data was deleted.'))
            self._write_counts('Would delete:', counts)
            return

        try:
            with transaction.atomic():
                self._delete_scoped_data(scope)
        except ProtectedError as exc:
            raise CommandError(
                'Cleanup stopped because a protected relationship prevented deletion. '
                'No database changes were committed.'
            ) from exc
        except Exception as exc:
            raise CommandError(
                'Cleanup failed before completion. No database changes were committed.'
            ) from exc

        self.stdout.write(self.style.SUCCESS('Test data cleanup completed successfully.'))
        self._write_counts('Deleted:', counts)

    def _scope(self):
        infrastructure_project_ids = set(
            InfrastructureProject.objects.filter(
                infrastructure_code__startswith=SEED_INFRASTRUCTURE_CODE_PREFIX,
            ).values_list('project_id', flat=True)
        )
        non_infrastructure_ids = set(
            NonInfrastructureProject.objects.filter(
                project__created_by_user__username__startswith=SEED_USER_PREFIX,
            ).values_list('pk', flat=True)
        )
        non_infrastructure_project_ids = set(
            NonInfrastructureProject.objects.filter(pk__in=non_infrastructure_ids).values_list(
                'project_id', flat=True,
            )
        )
        project_ids = infrastructure_project_ids | non_infrastructure_project_ids
        return {
            'infrastructure_project_ids': infrastructure_project_ids,
            'non_infrastructure_ids': non_infrastructure_ids,
            'non_infrastructure_project_ids': non_infrastructure_project_ids,
            'project_ids': project_ids,
        }

    def _counts(self, scope):
        infrastructure_ids = scope['infrastructure_project_ids']
        non_infrastructure_ids = scope['non_infrastructure_ids']
        project_ids = scope['project_ids']
        return {
            'Infrastructure projects': InfrastructureProject.objects.filter(
                project_id__in=infrastructure_ids,
            ).count(),
            'Non-Infrastructure projects': NonInfrastructureProject.objects.filter(
                project_id__in=non_infrastructure_ids,
            ).count(),
            'Shared projects': Project.objects.filter(
                project_id__in=project_ids,
            ).count(),
            'Project revisions': ProjectRevision.objects.filter(
                project_id__in=project_ids,
            ).count(),
            'Infrastructure progress updates': InfrastructureProgressUpdate.objects.filter(
                infrastructure__project_id__in=infrastructure_ids,
            ).count(),
            'Infrastructure schedules': InfrastructureSchedule.objects.filter(
                infrastructure__project_id__in=infrastructure_ids,
            ).count(),
            'Infrastructure financial records': FinancialRecord.objects.filter(
                infrastructure__project_id__in=infrastructure_ids,
            ).count(),
            'Project inspections': ProjectInspection.objects.filter(
                project_id__in=project_ids,
            ).count(),
            'Inspection evidence': InspectionEvidence.objects.filter(
                inspection__project_id__in=project_ids,
            ).count(),
            'Project images': ProjectImage.all_objects.filter(
                project_id__in=project_ids,
            ).count(),
            'Project reports': ProjectReport.objects.filter(
                project_id__in=project_ids,
            ).count(),
            'Non-Infrastructure progress updates': NonInfrastructureProgressUpdate.objects.filter(
                non_infrastructure_id__in=non_infrastructure_ids,
            ).count(),
            'Evidence records': NonInfrastructureEvidence.objects.filter(
                progress_update__non_infrastructure_id__in=non_infrastructure_ids,
            ).count(),
            'Test users': User.objects.filter(
                username__startswith=SEED_USER_PREFIX,
            ).count(),
        }

    def _delete_scoped_data(self, scope):
        infrastructure_ids = scope['infrastructure_project_ids']
        non_infrastructure_ids = scope['non_infrastructure_ids']
        project_ids = scope['project_ids']

        # Remove protected descendants before their progress/update parents.
        InspectionEvidence.objects.filter(
            inspection__project_id__in=project_ids,
        ).delete()
        ProjectInspection.objects.filter(project_id__in=project_ids).delete()
        NonInfrastructureEvidence.objects.filter(
            progress_update__non_infrastructure_id__in=non_infrastructure_ids,
        ).delete()
        NonInfrastructureProgressUpdate.objects.filter(
            non_infrastructure_id__in=non_infrastructure_ids,
        ).delete()

        InfrastructureProgressUpdate.objects.filter(
            infrastructure__project_id__in=infrastructure_ids,
        ).delete()
        InfrastructureSchedule.objects.filter(
            infrastructure__project_id__in=infrastructure_ids,
        ).delete()
        FinancialRecord.objects.filter(
            infrastructure__project_id__in=infrastructure_ids,
        ).delete()
        ProjectImage.all_objects.filter(project_id__in=project_ids).delete()
        ProjectReport.objects.filter(project_id__in=project_ids).delete()

        # Progress updates protect their linked revisions, so revisions come next.
        ProjectRevision.objects.filter(project_id__in=project_ids).delete()
        InfrastructureProject.objects.filter(project_id__in=infrastructure_ids).delete()
        NonInfrastructureProject.objects.filter(project_id__in=non_infrastructure_ids).delete()
        Project.objects.filter(project_id__in=project_ids).delete()

        # This is intentionally limited to the reserved users created by seed_projects.
        seed_users = User.objects.filter(username__startswith=SEED_USER_PREFIX)
        UserRole.objects.filter(user__in=seed_users).delete()
        seed_users.delete()

    def _write_counts(self, heading, counts):
        self.stdout.write(heading)
        for label, count in counts.items():
            self.stdout.write(f'  {label}: {count}')

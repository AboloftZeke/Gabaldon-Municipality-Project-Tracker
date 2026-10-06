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
SCOPE_NAMES = {
    'infra': 'Infrastructure',
    'non_infra': 'Non-Infrastructure',
    'users': 'Users',
    'all': 'All',
}


class Command(BaseCommand):
    help = 'Safely remove selected local test data without changing the database schema.'

    def add_arguments(self, parser):
        parser.add_argument('--infra', action='store_true', help='Clean Infrastructure data.')
        parser.add_argument('--non-infra', action='store_true', help='Clean Non-Infrastructure data.')
        parser.add_argument('--users', action='store_true', help='Clean eligible seed users only.')
        parser.add_argument('--all', action='store_true', help='Clean all eligible test data.')
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Permanently delete the selected data. Without this flag, run a dry run.',
        )

    def handle(self, *args, **options):
        scope_name = self._selected_scope(options)
        scope = self._scope(scope_name)
        counts = self._counts(scope_name, scope)
        scope_label = SCOPE_NAMES[scope_name]

        if not options['confirm']:
            self.stdout.write(self.style.WARNING('DRY RUN: No data was deleted.'))
            self.stdout.write(f'Scope: {scope_label}')
            self._write_counts('Would delete:', counts)
            return

        self.stdout.write(self.style.WARNING(
            'WARNING: This will permanently delete the selected test data.'
        ))
        self.stdout.write(f'Scope: {scope_label}')
        try:
            with transaction.atomic():
                self._delete_scope(scope_name, scope)
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
        self.stdout.write(f'Scope: {scope_label}')
        self._write_counts('Deleted:', counts)
        self._write_preserved(scope_name)

    def _selected_scope(self, options):
        selected = [
            name for name in ('infra', 'non_infra', 'users', 'all')
            if options[name]
        ]
        if not selected:
            raise CommandError(
                'Please specify one cleanup scope:\n'
                '  --infra\n'
                '  --non-infra\n'
                '  --users\n'
                '  --all'
            )
        if len(selected) > 1:
            raise CommandError('Cleanup scopes are mutually exclusive; specify exactly one.')
        return selected[0]

    def _scope(self, scope_name):
        include_infra = scope_name in {'infra', 'all'}
        include_non_infra = scope_name in {'non_infra', 'all'}
        infrastructure_project_ids = set()
        non_infrastructure_ids = set()
        non_infrastructure_project_ids = set()

        if include_infra:
            infrastructure_project_ids = set(
                InfrastructureProject.objects.values_list('project_id', flat=True)
            )
        if include_non_infra:
            non_infrastructure_ids = set(
                NonInfrastructureProject.objects.values_list('pk', flat=True)
            )
            non_infrastructure_project_ids = set(
                NonInfrastructureProject.objects.values_list('project_id', flat=True)
            )

        return {
            'infrastructure_project_ids': infrastructure_project_ids,
            'non_infrastructure_ids': non_infrastructure_ids,
            'non_infrastructure_project_ids': non_infrastructure_project_ids,
            'project_ids': infrastructure_project_ids | non_infrastructure_project_ids,
            'user_ids': set(
                User.objects.filter(username__startswith=SEED_USER_PREFIX)
                .values_list('pk', flat=True)
            ) if scope_name in {'users', 'all'} else set(),
        }

    def _counts(self, scope_name, scope):
        counts = {}
        infrastructure_ids = scope['infrastructure_project_ids']
        non_infrastructure_ids = scope['non_infrastructure_ids']
        project_ids = scope['project_ids']

        if scope_name in {'infra', 'all'}:
            counts.update({
                'Infrastructure projects': InfrastructureProject.objects.filter(
                    project_id__in=infrastructure_ids,
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
            })

        if scope_name in {'non_infra', 'all'}:
            counts.update({
                'Non-Infrastructure projects': NonInfrastructureProject.objects.filter(
                    pk__in=non_infrastructure_ids,
                ).count(),
                'Progress updates': NonInfrastructureProgressUpdate.objects.filter(
                    non_infrastructure_id__in=non_infrastructure_ids,
                ).count(),
                'Evidence records': NonInfrastructureEvidence.objects.filter(
                    progress_update__non_infrastructure_id__in=non_infrastructure_ids,
                ).count(),
            })

        if scope_name in {'infra', 'non_infra', 'all'}:
            counts.update({
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
                'Publication revisions': ProjectRevision.objects.filter(
                    project_id__in=project_ids,
                ).count(),
                'Shared project records': Project.objects.filter(
                    project_id__in=project_ids,
                ).count(),
            })

        if scope_name in {'users', 'all'}:
            counts['Test users'] = User.objects.filter(pk__in=scope['user_ids']).count()
        return counts

    def _delete_scope(self, scope_name, scope):
        if scope_name in {'infra', 'all'}:
            self._delete_infrastructure(scope)
        if scope_name in {'non_infra', 'all'}:
            self._delete_non_infrastructure(scope)
        if scope_name in {'users', 'all'}:
            self._delete_users(scope)

    def _delete_infrastructure(self, scope):
        project_ids = scope['infrastructure_project_ids']
        self._delete_project_dependents(project_ids)
        InfrastructureProgressUpdate.objects.filter(
            infrastructure__project_id__in=project_ids,
        ).delete()
        InfrastructureSchedule.objects.filter(
            infrastructure__project_id__in=project_ids,
        ).delete()
        FinancialRecord.objects.filter(
            infrastructure__project_id__in=project_ids,
        ).delete()
        ProjectRevision.objects.filter(project_id__in=project_ids).delete()
        InfrastructureProject.objects.filter(project_id__in=project_ids).delete()
        Project.objects.filter(project_id__in=project_ids).delete()

    def _delete_non_infrastructure(self, scope):
        non_infrastructure_ids = scope['non_infrastructure_ids']
        project_ids = scope['non_infrastructure_project_ids']
        NonInfrastructureEvidence.objects.filter(
            progress_update__non_infrastructure_id__in=non_infrastructure_ids,
        ).delete()
        NonInfrastructureProgressUpdate.objects.filter(
            non_infrastructure_id__in=non_infrastructure_ids,
        ).delete()
        self._delete_project_dependents(project_ids)
        ProjectRevision.objects.filter(project_id__in=project_ids).delete()
        NonInfrastructureProject.objects.filter(pk__in=non_infrastructure_ids).delete()
        Project.objects.filter(project_id__in=project_ids).delete()

    def _delete_project_dependents(self, project_ids):
        InspectionEvidence.objects.filter(inspection__project_id__in=project_ids).delete()
        ProjectInspection.objects.filter(project_id__in=project_ids).delete()
        ProjectImage.all_objects.filter(project_id__in=project_ids).delete()
        ProjectReport.objects.filter(project_id__in=project_ids).delete()

    def _delete_users(self, scope):
        seed_users = User.objects.filter(pk__in=scope['user_ids'])
        UserRole.objects.filter(user__in=seed_users).delete()
        seed_users.delete()

    def _write_counts(self, heading, counts):
        self.stdout.write(heading)
        for label, count in counts.items():
            self.stdout.write(f'  {label}: {count}')

    def _write_preserved(self, scope_name):
        preserved = {
            'infra': 'Non-Infrastructure data, users, and categories/reference data',
            'non_infra': 'Infrastructure data, users, and categories/reference data',
            'users': 'Infrastructure data, Non-Infrastructure data, and categories/reference data',
            'all': 'Categories/reference data, migrations, permissions, groups, and content types',
        }
        self.stdout.write('Preserved:')
        self.stdout.write(f'  {preserved[scope_name]}')

from copy import deepcopy
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import ProjectRevision
from .publication_service import publish_publication_revision
from .publication_snapshots import build_project_publication_snapshot
from .publication_workflow import PublicationStatus
from .test_head_operational_revisions import HeadOperationalRevisionTests


class FirstPublicationReadinessTests(TestCase):
    def _publish_current(self, project):
        return HeadOperationalRevisionTests._publish_current(self, project)

    def setUp(self):
        HeadOperationalRevisionTests.setUp(self)
        self.infrastructure_public.delete()
        self.non_infrastructure_public.delete()

    def approved_revision(self, project):
        return ProjectRevision.objects.create(
            project=project,
            revision_number=1,
            status=PublicationStatus.APPROVED,
            snapshot=build_project_publication_snapshot(project),
        )

    def test_infrastructure_first_publication_reports_all_missing_requirements(self):
        self.infrastructure.status = None
        self.infrastructure.physical_progress_percentage = None
        self.infrastructure.save(update_fields=[
            'status',
            'physical_progress_percentage',
        ])
        revision = self.approved_revision(self.infrastructure.project)
        snapshot = deepcopy(revision.snapshot)
        snapshot['inspection']['completion_percentage'] = None
        revision.snapshot = snapshot
        revision.save(update_fields=['snapshot'])

        with self.assertRaises(ValidationError) as caught:
            publish_publication_revision(
                revision,
                self.users['engineer', 'head'],
            )

        message = ' '.join(caught.exception.messages)
        self.assertIn('explicitly confirm the official status', message)
        self.assertIn('official status is required', message)
        self.assertIn('actual physical progress is required', message)
        self.assertIn('inspection completion percentage is required', message)
        revision.refresh_from_db()
        self.assertEqual(revision.status, PublicationStatus.APPROVED)
        self.assertFalse(revision.is_current_public)

    def test_head_confirmation_updates_only_operational_snapshot_values(self):
        revision = self.approved_revision(self.infrastructure.project)
        reviewed_title = revision.snapshot['infrastructure']['title']
        self.infrastructure.title = 'Unreviewed working title'
        self.infrastructure.save(update_fields=['title'])

        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.post(reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        ), {
            'status': 'completed',
            'physical_progress_percentage': '45',
            'cost_progress_percentage': '',
            'inspection_completion_percentage': '65',
        })
        self.assertEqual(response.status_code, 302)

        revision.refresh_from_db()
        infrastructure = revision.snapshot['infrastructure']
        self.assertEqual(infrastructure['title'], reviewed_title)
        self.assertEqual(infrastructure['status'], 'completed')
        self.assertEqual(infrastructure['physical_progress_percentage'], '45.00')
        self.assertIsNone(infrastructure['cost_progress_percentage'])
        self.assertEqual(
            revision.snapshot['inspection']['completion_percentage'],
            '65.00',
        )

        published = publish_publication_revision(
            revision,
            self.users['engineer', 'head'],
        )
        self.assertEqual(published.status, PublicationStatus.PUBLISHED)
        public_response = self.client.get(reverse(
            'public_infrastructure_project_detail',
            args=[self.infrastructure.pk],
        ))
        public_project = public_response.context['public_project']
        self.assertEqual(public_project['title'], reviewed_title)
        self.assertEqual(public_project['status'], 'completed')
        self.assertEqual(
            public_project['physical_progress_percentage'],
            Decimal('45.00'),
        )
        self.assertIsNone(public_project['cost_progress_percentage'])

    def test_non_infrastructure_default_status_requires_head_confirmation(self):
        revision = self.approved_revision(self.non_infrastructure.project)
        mayor_head = self.users['mayor', 'head']

        with self.assertRaises(ValidationError) as caught:
            publish_publication_revision(revision, mayor_head)
        self.assertIn(
            "Mayor's Office Head must explicitly confirm the official status",
            ' '.join(caught.exception.messages),
        )

        self.client.force_login(mayor_head)
        response = self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_operations',
            args=[self.non_infrastructure.pk],
        ), {'status': 'planned'})
        self.assertEqual(response.status_code, 302)
        revision.refresh_from_db()
        self.assertEqual(
            revision.snapshot['non_infrastructure']['status'],
            'planned',
        )
        published = publish_publication_revision(revision, mayor_head)
        self.assertEqual(published.status, PublicationStatus.PUBLISHED)

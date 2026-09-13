from datetime import date, timedelta
from copy import deepcopy
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (
    Infrastructure_Project,
    Non_Infrastructure_Project,
    Project,
    Project_Inspection,
    ProjectPublicationRevision,
    UserFlag,
)
from .publication_service import OPERATIONAL_CONFIRMATION_KEY
from .publication_snapshots import build_project_publication_snapshot


class PublicationOperationalUITests(TestCase):
    def setUp(self):
        self.users = {}
        for department, role in [
            ('engineer', 'staff'),
            ('engineer', 'head'),
            ('mayor', 'staff'),
            ('mayor', 'head'),
        ]:
            user = User.objects.create_user(
                f'{department}-{role}',
                password='test-password',
                is_staff=True,
            )
            UserFlag.objects.create(
                user=user,
                department=department,
                role=role,
            )
            self.users[department, role] = user
        self.admin = User.objects.create_superuser(
            'admin',
            password='test-password',
        )
        UserFlag.objects.create(
            user=self.admin,
            department='admin',
            role='admin',
        )

        infrastructure_base = Project.objects.create(
            project_type='infrastructure',
            created_by_user=self.users['engineer', 'staff'],
        )
        self.infrastructure = Infrastructure_Project.objects.create(
            project=infrastructure_base,
            infrastructure_title='Municipal Hall Rehabilitation',
            award_status='awarded',
            planned_start_date=date.today() - timedelta(days=5),
            planned_end_date=date.today() + timedelta(days=5),
        )
        self.inspection = Project_Inspection.objects.create(
            project=infrastructure_base,
            inspection_date=date.today(),
            completion_percentage=Decimal('30'),
        )
        self.infrastructure_revision = ProjectPublicationRevision.objects.create(
            project=infrastructure_base,
            revision_number=1,
            status='approved',
            snapshot_data=build_project_publication_snapshot(
                infrastructure_base,
            ),
        )
        incomplete_snapshot = deepcopy(
            self.infrastructure_revision.snapshot_data,
        )
        incomplete_snapshot['inspection']['completion_percentage'] = None
        self.infrastructure_revision.snapshot_data = incomplete_snapshot
        self.infrastructure_revision.save(update_fields=['snapshot_data'])

        non_infrastructure_base = Project.objects.create(
            project_type='non_infrastructure',
            created_by_user=self.users['mayor', 'staff'],
        )
        self.non_infrastructure = Non_Infrastructure_Project.objects.create(
            project=non_infrastructure_base,
            non_infra_name='Community Wellness Program',
        )
        self.non_infrastructure_revision = (
            ProjectPublicationRevision.objects.create(
                project=non_infrastructure_base,
                revision_number=1,
                status='approved',
                snapshot_data=build_project_publication_snapshot(
                    non_infrastructure_base,
                ),
            )
        )

    def revision_url(self, revision):
        return reverse('publication_revision_detail', args=[revision.pk])

    def test_engineering_head_sees_incomplete_readiness_and_direct_action(self):
        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.get(self.revision_url(
            self.infrastructure_revision,
        ))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['operational']['is_complete'])
        self.assertFalse(response.context['can_publish'])
        self.assertContains(response, 'Operational Information: Incomplete')
        self.assertContains(response, 'Actual Physical Progress')
        self.assertContains(response, 'Inspection Completion')
        self.assertContains(response, 'Expected / Scheduled Progress')
        self.assertContains(response, 'Variance')
        self.assertContains(response, 'Calculated Cost Progress')
        self.assertContains(response, 'Set Status &amp; Progress')
        self.assertContains(response, 'Operational Information Required')
        self.assertContains(
            response,
            'Complete operational information before publishing.',
        )
        self.assertNotContains(response, 'Publish to Public Dashboard')
        self.assertNotContains(response, 'Edit Project')

        queue = self.client.get(
            reverse('publication_review_queue'),
            {'status': 'approved'},
        )
        self.assertContains(queue, 'Complete Operational Information')
        self.assertNotContains(queue, 'Preview &amp; Publish')
        self.assertContains(queue, 'Approved submissions')

    def test_completed_infrastructure_readiness_enables_publish(self):
        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.post(reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        ), {
            'award_status': 'awarded',
            'physical_progress_percentage': '45',
            'cost_progress_percentage': '30',
            'inspection_completion_percentage': '50',
            'from_review': str(self.infrastructure_revision.pk),
        })
        self.assertRedirects(
            response,
            self.revision_url(self.infrastructure_revision),
        )

        self.infrastructure_revision.refresh_from_db()
        self.assertIn(
            OPERATIONAL_CONFIRMATION_KEY,
            self.infrastructure_revision.snapshot_data,
        )
        response = self.client.get(self.revision_url(
            self.infrastructure_revision,
        ))
        self.assertTrue(response.context['operational']['is_complete'])
        self.assertTrue(response.context['can_publish'])
        self.assertContains(response, 'Operational Information: Complete')
        self.assertContains(response, 'Entered Cost Progress')
        self.assertContains(response, 'Update Status &amp; Progress')
        self.assertContains(response, 'Publish to Public Dashboard')
        queue = self.client.get(
            reverse('publication_review_queue'),
            {'status': 'approved'},
        )
        self.assertContains(queue, 'Preview &amp; Publish')
        self.assertNotContains(queue, 'Complete Operational Information')

    def test_mayor_head_gets_status_only_readiness_workflow(self):
        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.get(self.revision_url(
            self.non_infrastructure_revision,
        ))
        self.assertFalse(response.context['operational']['is_complete'])
        self.assertContains(response, 'Operational Information: Incomplete')
        self.assertContains(response, 'Official Status')
        self.assertContains(response, 'Set Project Status')
        self.assertNotContains(response, 'Actual Physical Progress')
        self.assertNotContains(response, 'Publish to Public Dashboard')

        response = self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_operations',
            args=[self.non_infrastructure.pk],
        ), {
            'status': 'ongoing',
            'from_review': str(self.non_infrastructure_revision.pk),
        })
        self.assertRedirects(
            response,
            self.revision_url(self.non_infrastructure_revision),
        )
        response = self.client.get(self.revision_url(
            self.non_infrastructure_revision,
        ))
        self.assertTrue(response.context['operational']['is_complete'])
        self.assertContains(response, 'Update Project Status')
        self.assertContains(response, 'Publish to Public Dashboard')

    def test_operational_controls_are_scoped_to_heads(self):
        for user in [self.users['engineer', 'staff'], self.admin]:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse(
                    'engineering_projects:project_list',
                ))
                self.assertNotContains(response, 'Update Status &amp; Progress')

        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.get(reverse(
            'engineering_projects:project_list',
        ))
        self.assertContains(response, 'Update Status &amp; Progress')
        self.assertNotContains(response, '>Edit<', html=True)

        for user in [self.users['mayor', 'staff'], self.admin]:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse(
                    'mayor_projects:non_infrastructure_project_list',
                ))
                self.assertNotContains(response, '>Update Status<', html=True)

        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.get(reverse(
            'mayor_projects:non_infrastructure_project_list',
        ))
        self.assertContains(response, 'Update Status')
        self.assertNotContains(response, '>Edit<', html=True)

    def test_review_linked_forms_use_retained_revision_titles(self):
        self.infrastructure.infrastructure_title = 'Newer Staff Infra Title'
        self.infrastructure.save(update_fields=['infrastructure_title'])
        self.client.force_login(self.users['engineer', 'head'])
        response = self.client.get(reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        ), {'from_review': self.infrastructure_revision.pk})
        self.assertContains(response, 'Municipal Hall Rehabilitation')
        self.assertNotContains(response, 'Newer Staff Infra Title')
        self.assertContains(response, 'Operational Information')
        self.assertContains(response, 'Official Status')
        self.assertContains(response, 'Actual Physical Progress')
        self.assertContains(response, 'Entered Cost Progress')
        self.assertContains(response, 'Inspection Completion')
        self.assertContains(response, 'Calculated Reference')
        self.assertContains(response, 'Expected / Scheduled Progress')
        self.assertContains(response, 'Read-only')
        self.assertContains(response, 'Save Status &amp; Progress')
        self.assertContains(
            response,
            '/static/css/templates/core/operational_update.css?v=20260913-1',
        )

        self.non_infrastructure.non_infra_name = 'Newer Staff Program Title'
        self.non_infrastructure.save(update_fields=['non_infra_name'])
        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.get(reverse(
            'mayor_projects:non_infrastructure_project_operations',
            args=[self.non_infrastructure.pk],
        ), {'from_review': self.non_infrastructure_revision.pk})
        self.assertContains(response, 'Community Wellness Program')
        self.assertNotContains(response, 'Newer Staff Program Title')
        self.assertContains(response, 'Operational Information')
        self.assertContains(response, 'Official Status')
        self.assertContains(response, 'Save Status')
        self.assertContains(response, 'Back to Publication Review')
        self.assertNotContains(response, 'Calculated Reference')
        self.assertNotContains(
            response,
            'No operational percentage is stored for Non-Infrastructure projects.',
        )
        self.assertContains(
            response,
            '/static/css/templates/core/operational_update.css?v=20260913-1',
        )

    def test_head_dashboard_surfaces_published_project_update(self):
        self.infrastructure_revision.status = 'published'
        self.infrastructure_revision.is_current_public_revision = True
        self.infrastructure_revision.save(update_fields=[
            'status',
            'is_current_public_revision',
        ])
        self.infrastructure.infrastructure_title = 'Unpublished Staff Title'
        self.infrastructure.award_status = 'completed'
        self.infrastructure.save(update_fields=[
            'infrastructure_title',
            'award_status',
        ])
        self.client.force_login(self.users['engineer', 'head'])

        response = self.client.get(reverse('engineering_head_dashboard'))

        self.assertContains(response, 'Municipal Hall Rehabilitation')
        self.assertContains(response, 'Awarded')
        self.assertNotContains(response, 'Unpublished Staff Title')
        self.assertNotContains(response, 'Completed')
        self.assertContains(response, 'Update Status &amp; Progress')
        self.assertContains(response, reverse(
            'engineering_projects:project_operations',
            args=[self.infrastructure.pk],
        ))
        self.assertNotContains(response, 'Edit Project')

    def test_mayor_dashboard_uses_current_public_snapshot(self):
        self.non_infrastructure_revision.status = 'published'
        self.non_infrastructure_revision.is_current_public_revision = True
        self.non_infrastructure_revision.save(update_fields=[
            'status',
            'is_current_public_revision',
        ])
        self.non_infrastructure.non_infra_name = 'Unpublished Mayor Title'
        self.non_infrastructure.status = 'completed'
        self.non_infrastructure.save(update_fields=[
            'non_infra_name',
            'status',
        ])
        self.client.force_login(self.users['mayor', 'head'])

        response = self.client.get(reverse('mayor_head_dashboard'))

        self.assertContains(response, 'Community Wellness Program')
        self.assertContains(response, 'Planned')
        self.assertNotContains(response, 'Unpublished Mayor Title')
        self.assertNotContains(response, 'Completed')
        self.assertContains(response, 'Update Status')
        self.assertContains(response, reverse(
            'mayor_projects:non_infrastructure_project_operations',
            args=[self.non_infrastructure.pk],
        ))

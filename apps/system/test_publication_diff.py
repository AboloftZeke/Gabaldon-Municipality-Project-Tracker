from copy import deepcopy

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .publication_diff import compare_snapshots, revision_comparison
from .models import Project, ProjectPublicationRevision, UserFlag
from .publication_workflow import PublicationStatus


class SnapshotDiffTests(SimpleTestCase):
    def rows(self, before, after, section='infrastructure'):
        result = compare_snapshots({section: after}, {section: before})
        return {row['path']: row for row in result['sections'][0]['fields']}

    def test_initial_submission_has_no_fake_changes(self):
        result = compare_snapshots({'infrastructure': {'title': 'New'}, 'images': [{'id': 1, 'url': '/one.jpg'}]})
        self.assertEqual(result['change_count'], 0)

    def test_field_change_states(self):
        rows = self.rows(
            {'title': 'Old', 'description': 'Clear me', 'code': 'Same'},
            {'title': 'New', 'description': '', 'code': 'Same', 'procurement_method': 'bidding'},
        )
        self.assertEqual(rows['title']['state'], 'modified')
        self.assertEqual(rows['title']['before'], 'Old')
        self.assertEqual(rows['title']['after'], 'New')
        self.assertEqual(rows['description']['state'], 'removed')
        self.assertEqual(rows['code']['state'], 'unchanged')
        self.assertEqual(rows['procurement_method']['state'], 'added')

    def test_null_missing_and_empty_are_equivalent_but_zero_is_a_value(self):
        rows = self.rows({'description': None, 'beneficiaries': None}, {'description': '', 'beneficiaries': 0}, 'non_infrastructure')
        self.assertEqual(rows['description']['state'], 'unchanged')
        self.assertEqual(rows['beneficiaries']['state'], 'added')
        self.assertEqual(rows['beneficiaries']['after'], '0')

    def test_infrastructure_nested_values_and_metadata(self):
        rows = self.rows(
            {'id': 1, 'updated_at': 'old', 'address': {'id': 1, 'street': 'Old'}, 'physical_progress_percentage': '10.00'},
            {'id': 2, 'updated_at': 'new', 'address': {'id': 2, 'street': 'New'}, 'physical_progress_percentage': '10'},
        )
        self.assertEqual(set(rows), {'address.street', 'physical_progress_percentage'})
        self.assertTrue(rows['address.street']['changed'])
        self.assertFalse(rows['physical_progress_percentage']['changed'])

    def test_removed_nested_section_and_named_relationship(self):
        rows = self.rows({'address': {'street': 'Old'}, 'category': {'id': 1, 'name': 'Road'}}, {'address': None, 'category': None})
        self.assertEqual(rows['address.street']['state'], 'removed')
        self.assertEqual(rows['category']['before'], 'Road')
        self.assertEqual(rows['category']['state'], 'removed')

    def test_non_infrastructure_event_and_status(self):
        rows = self.rows({'event_date': '2026-09-01', 'status': 'planned', 'status_label': 'Planned'}, {'event_date': '2026-09-02', 'status': 'completed', 'status_label': 'Completed'}, 'non_infrastructure')
        self.assertEqual(rows['event_date']['state'], 'modified')
        self.assertEqual(rows['status']['after'], 'Completed')
        self.assertNotIn('status_label', rows)

    def test_images_added_removed_and_cover_changed(self):
        old = {'images': [{'id': 1, 'url': '/1', 'is_cover': True}, {'id': 2, 'url': '/2'}]}
        new = {'images': [{'id': 1, 'url': '/1', 'is_cover': False}, {'id': 3, 'url': '/3'}]}
        result = compare_snapshots(new, old)
        self.assertEqual([row['state'] for row in result['images']], ['modified', 'added', 'removed'])

    def test_image_order_and_capture_time_do_not_count_as_changes(self):
        old = {'images': [{'url': '/1', 'created_at': 'old'}, {'id': 2, 'url': '/2'}]}
        new = {'images': [{'id': 2, 'url': '/2'}, {'url': '/1', 'created_at': 'new'}]}
        self.assertEqual(compare_snapshots(new, old)['change_count'], 0)

    def test_changed_display_label_is_visible_even_when_code_is_unchanged(self):
        rows = self.rows({'status': 'planned', 'status_label': 'Planned'}, {'status': 'planned', 'status_label': 'Scheduled'}, 'non_infrastructure')
        self.assertEqual(rows['status']['state'], 'modified')
        self.assertEqual(rows['status']['before'], 'Planned')
        self.assertEqual(rows['status']['after'], 'Scheduled')

    def test_financial_and_schedule_sections_include_cleared_values(self):
        result = compare_snapshots(
            {'financial': {'approved_budget': '0'}, 'schedule': None},
            {'financial': {'approved_budget': '1000.00'}, 'schedule': {'posting_date': '2026-09-01'}},
        )
        funding, schedule = result['sections']
        self.assertEqual(funding['fields'][0]['after'], '₱0.00')
        self.assertEqual(schedule['fields'][0]['state'], 'removed')
        self.assertEqual(schedule['fields'][0]['before'], 'Sep 01, 2026')


class PublicationComparisonViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('diff-admin', 'diff@example.com', 'password')
        self.project = Project.objects.create(project_type='infrastructure', created_by_user=self.admin)
        self.snapshot = {
            'project': {'id': self.project.pk, 'type': 'infrastructure'},
            'infrastructure': {'id': 1, 'title': 'Published title', 'description': 'Old description', 'code': 'INF-1'},
            'images': [{'id': 1, 'url': '/media/old.jpg', 'is_cover': True}],
        }
        self.head = User.objects.create_user('diff-head', is_staff=True)
        UserFlag.objects.create(user=self.head, department='engineer', role='head')
        self.client.force_login(self.head)

    def revision(self, number, status, snapshot=None, **kwargs):
        return ProjectPublicationRevision.objects.create(
            project=self.project, revision_number=number, status=status,
            snapshot_data=deepcopy(snapshot if snapshot is not None else self.snapshot), **kwargs,
        )

    def detail(self, revision):
        return self.client.get(reverse('publication_revision_detail', args=[revision.pk]))

    def test_first_submission_is_initial_even_after_rejected_submission(self):
        self.revision(1, PublicationStatus.REJECTED)
        pending = self.revision(2, PublicationStatus.PENDING_REVIEW)
        response = self.detail(pending)
        self.assertContains(response, 'Initial Publication Submission')
        self.assertNotContains(response, 'Previously published')
        self.assertEqual(response.context['comparison']['change_count'], 0)

    def test_baseline_is_current_public_not_supersedes_or_latest_revision(self):
        archived = self.revision(1, PublicationStatus.ARCHIVED)
        current_snapshot = deepcopy(self.snapshot)
        current_snapshot['infrastructure']['title'] = 'Actual current public title'
        current = self.revision(2, PublicationStatus.PUBLISHED, current_snapshot, is_current_public_revision=True)
        pending = self.revision(3, PublicationStatus.PENDING_REVIEW, supersedes_revision=archived)
        self.revision(4, PublicationStatus.REJECTED)
        comparison = revision_comparison(pending)
        self.assertEqual(comparison['baseline'], current)
        response = self.detail(pending)
        self.assertContains(response, 'Actual current public title')
        self.assertContains(response, 'Previously published')
        self.assertContains(response, 'Newly submitted')
        self.assertContains(response, 'snapshot-change--modified')

    def test_removed_added_images_and_values_survive_invalid_review_form(self):
        self.revision(1, PublicationStatus.PUBLISHED, is_current_public_revision=True)
        submitted = deepcopy(self.snapshot)
        submitted['infrastructure'].update(description='', contractor={'id': 1, 'name': 'New contractor'})
        submitted['images'] = [{'id': 2, 'url': '/media/new.jpg', 'is_cover': True}]
        pending = self.revision(2, PublicationStatus.PENDING_REVIEW, submitted)
        response = self.client.post(reverse('publication_revision_review', args=[pending.pk]), {'decision': 'needs_revision', 'notes': ''})
        for text in ('snapshot-change--added', 'snapshot-change--removed', 'Cleared', '/media/old.jpg', '/media/new.jpg', 'New contractor'):
            self.assertContains(response, text, status_code=400)
        pending.refresh_from_db()
        self.assertEqual(pending.status, PublicationStatus.PENDING_REVIEW)

    def test_no_current_baseline_after_archive_is_not_initial(self):
        self.revision(1, PublicationStatus.ARCHIVED)
        pending = self.revision(2, PublicationStatus.PENDING_REVIEW)
        response = self.detail(pending)
        self.assertContains(response, 'No Current Published Revision')
        self.assertNotContains(response, 'Initial Publication Submission')
        self.assertEqual(response.context['comparison']['change_count'], 0)

    def test_current_revision_and_unchanged_submission_have_no_highlights(self):
        current = self.revision(1, PublicationStatus.PUBLISHED, is_current_public_revision=True)
        self.assertContains(self.detail(current), 'Current Published Revision')
        pending = self.revision(2, PublicationStatus.PENDING_REVIEW)
        response = self.detail(pending)
        self.assertContains(response, 'No changes from the current published version.')
        self.assertNotContains(response, 'snapshot-change--')

    def test_non_infrastructure_comparison_and_html_escaping(self):
        UserFlag.objects.filter(user=self.head).update(department='mayor')
        self.project.project_type = 'non_infrastructure'
        self.project.save(update_fields=['project_type'])
        old = {'project': {'type': 'non_infrastructure'}, 'non_infrastructure': {'id': 1, 'title': 'Program', 'beneficiaries': 20, 'address': {'street': 'Old street'}}}
        self.revision(1, PublicationStatus.PUBLISHED, old, is_current_public_revision=True)
        new = deepcopy(old)
        new['non_infrastructure'].update(beneficiaries=0, title='<script>alert(1)</script>', address=None)
        pending = self.revision(2, PublicationStatus.PENDING_REVIEW, new)
        response = self.detail(pending)
        self.assertContains(response, 'Program Information')
        self.assertContains(response, 'Old street')
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertEqual(response.context['comparison']['change_count'], 3)

    def test_employee_cannot_read_comparison(self):
        employee = User.objects.create_user('diff-employee', password='password', is_staff=True)
        pending = self.revision(1, PublicationStatus.PENDING_REVIEW)
        self.client.force_login(employee)
        self.assertEqual(self.detail(pending).status_code, 403)

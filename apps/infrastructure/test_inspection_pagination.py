from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.infrastructure import test_inspections as inspection_tests
from apps.system.models import InspectionEvidence, Project, ProjectInspection
from apps.system.tests import publish_current_snapshot


class PaginationLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href', '').endswith('#inspection-history'):
            self.links.append(attrs['href'])


class InspectionHistoryPaginationTests(TestCase):
    detail_url = inspection_tests.InfrastructureInspectionHistoryTests.detail_url

    def setUp(self):
        inspection_tests.InfrastructureInspectionHistoryTests.setUp(self)
        self.client.force_login(self.staff)

    def records(self, count):
        return [ProjectInspection.objects.create(
            project=self.infrastructure.project,
            inspection_date=date(2026, 1, 1) + timedelta(days=index),
            inspected_by_user=self.staff,
            completion_percentage=index,
            findings=f'Inspection findings {index}',
            remarks=f'Inspection remarks {index}',
        ) for index in range(count)]

    def test_thirteen_records_have_pages_of_five_five_and_three_newest_first(self):
        expected = list(reversed(self.records(13)))
        for number, start, end in ((1, 0, 5), (2, 5, 10), (3, 10, 13)):
            with self.subTest(page=number):
                response = self.client.get(self.detail_url, {'inspection_page': number})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(list(response.context['inspection_history']), expected[start:end])
                self.assertContains(response, 'class="inspection-card"', count=end - start)
                self.assertContains(response, f'Showing inspections {start + 1}–{end} of 13')
                self.assertContains(response, f'Page {number} of 3')
                self.assertContains(response, 'aria-current="page"')
                self.assertContains(response, 'id="inspection-history"', count=1)
                self.assertEqual(response.context['inspection_page'].paginator.count, 13)

    def test_default_page_contains_five_newest_records(self):
        records = self.records(6)
        response = self.client.get(self.detail_url)
        self.assertEqual(list(response.context['inspection_history']), list(reversed(records[1:])))
        self.assertContains(response, 'aria-label="Next page of inspection history"')
        self.assertNotContains(response, 'aria-label="Previous page of inspection history"')

    def test_equal_dates_order_by_creation_time_then_id_across_pages(self):
        records = self.records(7)
        shared_date, shared_time = date(2026, 2, 1), timezone.now()
        ProjectInspection.objects.filter(project=self.infrastructure.project).update(
            inspection_date=shared_date, created_at=shared_time,
        )
        ProjectInspection.objects.filter(pk=records[0].pk).update(created_at=shared_time + timedelta(seconds=1))
        expected = [records[0]] + list(reversed(records[1:]))
        first = self.client.get(self.detail_url)
        second = self.client.get(self.detail_url, {'inspection_page': 2})
        self.assertEqual(list(first.context['inspection_history']) + list(second.context['inspection_history']), expected)
        self.assertEqual(first.context['inspection_history'].query.order_by, ('-inspection_date', '-created_at', '-inspection_id'))

    def test_empty_history_keeps_empty_state_without_controls(self):
        response = self.client.get(self.detail_url)
        self.assertContains(response, 'No inspections recorded')
        self.assertContains(response, '0 inspections')
        self.assertNotContains(response, 'class="inspection-card"')
        self.assertNotContains(response, 'aria-label="Inspection history pages"')

    def test_single_page_uses_total_count_without_navigation(self):
        self.records(5)
        response = self.client.get(self.detail_url)
        self.assertContains(response, 'Showing inspections 1–5 of 5')
        self.assertNotContains(response, 'aria-label="Inspection history pages"')

    def test_invalid_page_values_use_paginator_get_page_fallbacks(self):
        records = list(reversed(self.records(13)))
        for value, expected_number in (('', 1), ('abc', 1), ('1.5', 1), ('-1', 3), ('0', 3), ('999', 3)):
            with self.subTest(value=value):
                response = self.client.get(self.detail_url, {'inspection_page': value})
                page = response.context['inspection_page']
                self.assertEqual(response.status_code, 200)
                self.assertEqual(page.number, expected_number)
                start = (expected_number - 1) * 5
                self.assertEqual(list(response.context['inspection_history']), records[start:start + 5])

    def test_pagination_preserves_all_parameters_and_replaces_its_own_key(self):
        self.records(13)
        response = self.client.get(self.detail_url + '?inspection_page=1&inspection_page=2&page=7&search=bridge+%26+road&tag=a&tag=b&blank=')
        links = PaginationLinks(response.content.decode()).links
        self.assertEqual(len(links), 2)
        for link, expected in zip(links, ('1', '3')):
            parsed = urlsplit(link)
            self.assertEqual(parsed.fragment, 'inspection-history')
            self.assertEqual(parse_qs(parsed.query, keep_blank_values=True), {
                'inspection_page': [expected], 'page': ['7'],
                'search': ['bridge & road'], 'tag': ['a', 'b'], 'blank': [''],
            })

    def test_evidence_is_prefetched_only_for_current_history_page_and_stays_grouped(self):
        records = self.records(13)
        other = ProjectInspection.objects.create(project=Project.objects.create(project_type='infrastructure'), inspection_date='2026-01-01', completion_percentage=0)
        for inspection in records + [other]:
            for kind, suffix in (('image', 'jpg'), ('document', 'pdf')):
                name = f'inspection-{inspection.pk}.{suffix}'
                InspectionEvidence.objects.create(
                    inspection=inspection, evidence_type=kind, original_name=name,
                    storage_name=f'inspections/{name}', file_url=f'/media/inspections/{name}',
                    uploaded_by_user=self.staff,
                )
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.detail_url, {'inspection_page': 2})
        shown = list(reversed(records))[5:10]
        for inspection in records + [other]:
            for suffix in ('jpg', 'pdf'):
                name = f'inspection-{inspection.pk}.{suffix}'
                if inspection in shown:
                    self.assertContains(response, name)
                else:
                    self.assertNotContains(response, name)
        for inspection in response.context['inspection_history']:
            self.assertEqual({item.inspection_id for item in inspection.evidence.all()}, {inspection.pk})
        history_queries = [q['sql'] for q in queries if '"system_project_inspection"' in q['sql'] and 'LIMIT 5' in q['sql']]
        self.assertEqual(len(history_queries), 1)
        self.assertIn('OFFSET 5', history_queries[0])
        self.assertIn('JOIN "auth_user"', history_queries[0])
        evidence_queries = [q['sql'] for q in queries if 'FROM "system_inspection_evidence"' in q['sql']]
        self.assertEqual(len(evidence_queries), 1)
        self.assertIn(' IN (' + ', '.join(str(i.pk) for i in shown) + ')', evidence_queries[0])
        self.assertContains(response, 'data-image-viewer-trigger', count=5)
        self.assertContains(response, 'data-image-viewer-image')
        self.assertContains(response, 'aria-label="Close image preview"')
        self.assertContains(response, 'class="evidence-document-card"', count=5)

    def test_staff_actions_and_read_only_head_and_admin_access_are_preserved(self):
        self.records(6)
        for user, editable in ((self.staff, True), (self.head, False), (self.admin, False)):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(self.detail_url, {'inspection_page': 2})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['can_manage_inspections'], editable)
                if editable:
                    self.assertContains(response, 'Edit Inspection', count=1)
                    self.assertContains(response, 'Add Inspection')
                else:
                    self.assertNotContains(response, 'Edit Inspection')
                    self.assertNotContains(response, 'Add Inspection')
        self.client.force_login(self.mayor_head)
        self.assertEqual(self.client.get(self.detail_url, {'inspection_page': 2}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.detail_url, {'inspection_page': 2}).status_code, 302)

    def test_public_detail_does_not_expose_internal_paginated_history(self):
        self.records(13)
        publish_current_snapshot(self.infrastructure.project)
        self.client.logout()
        response = self.client.get(reverse('public_infrastructure_project_detail', args=[self.infrastructure.pk]), {'inspection_page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="inspection-history"')
        self.assertNotContains(response, 'Inspection findings 0')
        self.assertNotIn('inspection_page', response.context)

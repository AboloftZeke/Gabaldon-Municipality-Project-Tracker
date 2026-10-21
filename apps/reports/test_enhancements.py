from copy import deepcopy
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase
from django.urls import reverse
from reportlab.lib.units import mm
from PIL import Image as PillowImage

from apps.reports import tests as fixtures
from apps.reports.pdf import _local_image, build_individual_report_pdf, build_summary_report_pdf
from apps.reports.presentation import disclosed_evidence_images, report_preparer
from apps.reports.services import (
    get_infrastructure_project_report_data, get_non_infrastructure_project_report_data,
    get_non_infrastructure_summary_report_data,
)
from apps.system.models import ProjectImage, ProjectReport


class ReportEnhancementTests(TestCase):
    infrastructure_snapshot = fixtures.ReportAccessTests.infrastructure_snapshot
    non_infrastructure_snapshot = fixtures.ReportAccessTests.non_infrastructure_snapshot
    create_published_revision = fixtures.ReportAccessTests.create_published_revision
    create_unpublished_revision = fixtures.ReportAccessTests.create_unpublished_revision
    create_non_current_published_revision = fixtures.ReportAccessTests.create_non_current_published_revision

    def setUp(self):
        fixtures.ReportAccessTests.setUp(self)

    def image(self, name, size=(1200, 400), color='blue'):
        output = BytesIO()
        PillowImage.new('RGB', size, color).save(output, 'PNG')
        return default_storage.save(name, ContentFile(output.getvalue()))

    def published_fields(self):
        snapshot = deepcopy(self.non_infrastructure_revision.snapshot)
        snapshot['non_infrastructure'].update(target_beneficiaries='Farmer Cooperatives', sponsored_by='Published Foundation')
        self.non_infrastructure_revision.snapshot = snapshot
        self.non_infrastructure_revision.save(update_fields=['snapshot'])

    def generate(self, scope='non_infrastructure', extra=None):
        user = self.users['mayor' if scope == 'non_infrastructure' else 'engineer', 'head']
        self.client.force_login(user)
        pk = 202 if scope == 'non_infrastructure' else 101
        response = self.client.post(reverse(f'reports:{scope}_project_generate', args=[pk]), extra or {})
        self.assertEqual(response.status_code, 302)
        generated = ProjectReport.objects.latest('report_id')
        with default_storage.open(generated.file_url, 'rb') as source:
            return generated, source.read()

    def test_pdf_contains_municipal_identity_logo_and_beneficiary_sponsor(self):
        self.published_fields()
        _, content = self.generate()
        for text in (b'Municipality of Gabaldon', b'Nueva Ecija', b'BENEFICIARY TYPE', b'Farmer Cooperatives', b'SPONSORED BY', b'Published Foundation'):
            self.assertIn(text, content)
        self.assertIn(b'/Subtype /Image', content)

    def test_blank_sponsor_is_omitted_in_pdf_and_preview(self):
        _, content = self.generate()
        self.assertNotIn(b'Sponsored By', content)
        response = self.client.get(reverse('reports:non_infrastructure_project', args=[202]))
        self.assertNotContains(response, 'Sponsored By')

    def test_published_financial_procurement_and_remarks_remain_available(self):
        snapshot = deepcopy(self.non_infrastructure_revision.snapshot)
        snapshot['non_infrastructure'].update(
            project_cost='123456.00', fund_source='Municipal Activity Fund',
            contractor_supplier='Disclosed Supplier', quantity=25,
            procurement_description='Approved training kits', remarks='Disclosed program remarks',
        )
        self.non_infrastructure_revision.snapshot = snapshot
        self.non_infrastructure_revision.save(update_fields=['snapshot'])
        _, content = self.generate()
        for text in (b'123,456.00', b'Municipal Activity Fund', b'Disclosed Supplier', b'Approved training kits', b'Disclosed program remarks'):
            self.assertIn(text, content)
        response = self.client.get(reverse('reports:non_infrastructure_project', args=[202]))
        self.assertContains(response, 'Disclosed Supplier')
        self.assertContains(response, 'Approved training kits')
        self.assertContains(response, 'Disclosed program remarks')

    def test_authenticated_preparer_cannot_be_spoofed(self):
        user = self.users['mayor', 'head']
        user.first_name, user.last_name = 'Maria', 'Santos'
        user.save()
        generated, content = self.generate(extra={'generated_by': self.users['engineer', 'head'].pk, 'prepared_by': 'Spoofed Name'})
        self.assertEqual(content.count(b'Prepared by:'), 1)
        self.assertIn(b'Maria Santos', content)
        self.assertIn(b'Head', content)
        self.assertEqual(report_preparer(user)['position'], "Head · Mayor's Office")
        # Paragraph text runs may split at an escaped apostrophe in the PDF.
        self.assertIn(b'Mayor', content)
        self.assertIn(b's Office', content)
        self.assertNotIn(b'Spoofed Name', content)
        self.assertIn(user.username, generated.notes)

    def test_username_fallback_and_anonymous_identity_rejected(self):
        user = self.users['engineer', 'head']
        self.assertEqual(report_preparer(user)['name'], user.username)
        with self.assertRaises(PermissionDenied):
            report_preparer(AnonymousUser())

    def test_image_resizing_preserves_aspect_ratio_and_page_bounds(self):
        for index, size in enumerate(((2000, 500), (500, 2000), (100, 100))):
            with self.subTest(size=size):
                path = self.image(f'projects/aspect-{index}.png', size)
                image = _local_image(default_storage.url(path))
                self.assertIsNotNone(image)
                self.assertLessEqual(image.drawWidth, 170 * mm)
                self.assertLessEqual(image.drawHeight, 85 * mm)
                self.assertAlmostEqual(image.drawWidth / image.drawHeight, size[0] / size[1], places=2)

    def test_multiple_published_images_render_and_missing_corrupt_files_are_skipped(self):
        first = self.image('projects/first.png', color='red')
        second = self.image('projects/second.png', color='green')
        broken = default_storage.save('projects/broken.png', ContentFile(b'not an image'))
        snapshot = deepcopy(self.infrastructure_revision.snapshot)
        snapshot['images'] = [{'id': i, 'url': url, 'is_cover': False} for i, url in enumerate([
            '/media/projects/missing.png', default_storage.url(broken), default_storage.url(first), default_storage.url(second),
        ])]
        self.infrastructure_revision.snapshot = snapshot
        self.infrastructure_revision.save(update_fields=['snapshot'])
        _, content = self.generate('infrastructure')
        self.assertGreaterEqual(content.count(b'/Subtype /Image'), 3)  # municipal logo + two photos
        self.assertIn(b'Project image 2', content)

    def test_storage_failure_is_skipped_and_external_urls_are_never_fetched(self):
        with patch('apps.reports.pdf.default_storage.exists', side_effect=OSError('offline')):
            self.assertIsNone(_local_image('/media/projects/photo.png'))
        self.assertIsNone(_local_image('https://example.com/private.png'))
        self.assertIsNone(_local_image('/media/../private.png'))

    def test_inspection_evidence_uses_published_selected_inspections_only(self):
        path = self.image('inspections/selected.png')
        snapshot = deepcopy(self.infrastructure_revision.snapshot)
        snapshot['progress_update'] = {'supporting_inspections': [{
            'id': 5, 'inspection_date': '2026-08-10', 'evidence': [
                {'type': 'image', 'url': default_storage.url(path), 'original_name': 'Published inspection photo'},
                {'type': 'document', 'url': '/media/private.pdf', 'original_name': 'Private document'},
            ],
        }]}
        self.infrastructure_revision.snapshot = snapshot
        self.infrastructure_revision.save(update_fields=['snapshot'])
        ProjectImage.objects.create(project=self.infrastructure_revision.project, image_url='/media/projects/unpublished.png')
        report = get_infrastructure_project_report_data(101)
        self.assertEqual(len(report['evidence_images']), 1)
        _, content = self.generate('infrastructure')
        self.assertIn(b'Published inspection photo', content)
        self.assertNotIn(b'Private document', content)
        self.assertNotIn(b'unpublished', content)

    def test_noninfra_only_approved_retained_supporting_images_render(self):
        path = self.image('non_infrastructure/evidence/approved.png')
        snapshot = deepcopy(self.non_infrastructure_revision.snapshot)
        snapshot['non_infrastructure_progress_update'] = {
            'review_status': 'approved', 'evidence': [
                {'file_path': path, 'description': 'Approved activity photo'},
                {'file_path': 'non_infrastructure/evidence/../../private.png', 'description': 'Unsafe'},
            ],
        }
        self.non_infrastructure_revision.snapshot = snapshot
        self.non_infrastructure_revision.save(update_fields=['snapshot'])
        report = get_non_infrastructure_project_report_data(202)
        self.assertEqual(len(report['evidence_images']), 1)
        _, content = self.generate()
        self.assertIn(b'Approved activity photo', content)
        for status in ('draft', 'pending_review', 'returned', 'rejected', ''):
            with self.subTest(status=status):
                snapshot['non_infrastructure_progress_update']['review_status'] = status
                self.assertEqual(disclosed_evidence_images('non_infrastructure', snapshot), [])

    def test_unauthorized_update_evidence_is_absent_from_generated_report(self):
        path = self.image('non_infrastructure/evidence/returned.png')
        snapshot = deepcopy(self.non_infrastructure_revision.snapshot)
        snapshot['non_infrastructure_progress_update'] = {
            'review_status': 'returned',
            'evidence': [{'file_path': path, 'description': 'Returned private photograph'}],
        }
        self.non_infrastructure_revision.snapshot = snapshot
        self.non_infrastructure_revision.save(update_fields=['snapshot'])
        _, content = self.generate()
        self.assertNotIn(b'Returned private photograph', content)
        self.assertEqual(get_non_infrastructure_project_report_data(202)['evidence_images'], [])

    def test_implementation_dates_are_used_in_individual_and_summary_reports(self):
        snapshot = deepcopy(self.non_infrastructure_revision.snapshot)
        snapshot['non_infrastructure'].update(
            implementation_start_date='2026-10-01', implementation_end_date='2026-10-15',
            event_date=None,
        )
        self.non_infrastructure_revision.snapshot = snapshot
        self.non_infrastructure_revision.save(update_fields=['snapshot'])
        _, content = self.generate()
        self.assertIn(b'October 01, 2026', content)
        self.assertIn(b'October 15, 2026', content)
        summary = get_non_infrastructure_summary_report_data({})
        content = build_summary_report_pdf('non_infrastructure', summary, [])
        self.assertIn(b'October 01, 2026', content)

    def test_infrastructure_report_preserves_disclosed_actual_expenditure(self):
        snapshot = deepcopy(self.infrastructure_revision.snapshot)
        snapshot['financial']['actual_expenditure'] = '765432.10'
        self.infrastructure_revision.snapshot = snapshot
        self.infrastructure_revision.save(update_fields=['snapshot'])
        _, content = self.generate('infrastructure')
        self.assertIn(b'765,432.10', content)
        response = self.client.get(reverse('reports:infrastructure_project', args=[101]))
        self.assertContains(response, 'Actual Expenditure')
        self.assertContains(response, '765,432.10')

    def test_summary_has_logo_new_fields_and_one_final_signatory(self):
        self.published_fields()
        self.client.force_login(self.users['mayor', 'head'])
        response = self.client.post(reverse('reports:non_infrastructure_summary_generate'))
        self.assertEqual(response.status_code, 302)
        generated = ProjectReport.objects.latest('report_id')
        with default_storage.open(generated.file_url, 'rb') as source:
            content = source.read()
        self.assertIn(b'Farmer Cooperatives', content)
        self.assertIn(b'Published Foundation', content)
        self.assertIn(b'/Subtype /Image', content)
        self.assertEqual(content.count(b'Prepared by:'), 1)
        self.assertGreater(content.index(b'Prepared by:'), content.index(b'Published Foundation'))

    def test_long_text_multiple_images_do_not_overflow_pdf_layout(self):
        path = self.image('projects/long-report.png')
        report = get_non_infrastructure_project_report_data(202)
        report['remarks'] = 'Long remarks with retained details. ' * 100
        report['target_beneficiaries'] = 'BeneficiariesWithoutSpaces' * 75
        report['images'] = [{'image_url': default_storage.url(path), 'caption': f'Image {i}'} for i in range(15)]
        content = build_individual_report_pdf('non_infrastructure', report, prepared_by={'name': 'Authorized User', 'position': 'Head'})
        self.assertTrue(content.startswith(b'%PDF-'))
        self.assertIn(b'Image 11', content)
        self.assertNotIn(b'Image 12', content)
        self.assertEqual(content.count(b'Prepared by:'), 1)

import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.system.models import InspectionEvidence, Project_Inspection, UserFlag


class InfrastructureInspectionHistoryTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, True)

        from apps.infrastructure.tests import InfrastructureProjectFormTests

        fixture = InfrastructureProjectFormTests()
        fixture.setUp()
        self.staff = fixture.user
        self.staff.is_staff = True
        self.staff.save(update_fields=['is_staff'])
        UserFlag.objects.create(
            user=self.staff,
            department='engineer',
            role='staff',
        )
        self.infrastructure = fixture.create_project()

        self.head = get_user_model().objects.create_user(
            'engineering-head',
            is_staff=True,
        )
        UserFlag.objects.create(
            user=self.head,
            department='engineer',
            role='head',
        )
        self.mayor_head = get_user_model().objects.create_user(
            'mayor-head',
            is_staff=True,
        )
        UserFlag.objects.create(
            user=self.mayor_head,
            department='mayor',
            role='head',
        )
        self.admin = get_user_model().objects.create_superuser('admin')

    @property
    def create_url(self):
        return reverse(
            'engineering_projects:inspection_create',
            args=[self.infrastructure.pk],
        )

    @property
    def detail_url(self):
        return reverse(
            'engineering_projects:project_detail',
            args=[self.infrastructure.pk],
        )

    def add_inspection(self, inspection_date, completion, findings):
        return self.client.post(self.create_url, {
            'inspection_date': inspection_date,
            'completion_percentage': completion,
            'findings': findings,
            'remarks': f'Remarks for {findings}',
        })

    def test_staff_adds_multiple_inspections_without_overwriting_history(self):
        self.client.force_login(self.staff)

        first_response = self.add_inspection(
            '2026-06-01',
            '35.00',
            'Foundation inspected',
        )
        second_response = self.add_inspection(
            '2026-06-15',
            '48.50',
            'Structural work inspected',
        )

        self.assertRedirects(first_response, self.detail_url)
        self.assertRedirects(second_response, self.detail_url)
        inspections = list(
            self.infrastructure.project.inspections.order_by(
                'inspection_date',
            )
        )
        self.assertEqual(len(inspections), 2)
        self.assertEqual(inspections[0].findings, 'Foundation inspected')
        self.assertEqual(
            inspections[0].completion_percentage,
            Decimal('35.00'),
        )
        self.assertEqual(
            inspections[1].completion_percentage,
            Decimal('48.50'),
        )
        self.assertEqual(inspections[0].inspected_by_user, self.staff)
        self.assertEqual(inspections[1].inspected_by_user, self.staff)
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, 'Add Inspection')
        self.assertContains(detail, 'Edit Inspection', count=2)
        self.assertContains(detail, 'class="inspection-card"', count=2)

    def test_inspection_form_uses_clear_workflow_sections(self):
        self.client.force_login(self.staff)

        response = self.client.get(self.create_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Inspection Details')
        self.assertContains(response, 'Field Observations')
        self.assertContains(response, 'Supporting Evidence')
        self.assertContains(response, 'No evidence attached yet')
        self.assertContains(
            response,
            '/static/css/templates/projects/inspection_form.css?v=20260914-1',
        )

    def test_history_is_newest_first_and_visible_to_engineering_head(self):
        Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date='2026-05-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('20.00'),
            findings='Older inspection',
            remarks='Older remarks',
        )
        newest = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date='2026-06-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('40.00'),
            findings='Newest inspection',
            remarks='Newest remarks',
        )
        self.client.force_login(self.head)

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['inspection_history'])[0], newest)
        self.assertContains(response, 'Inspection History')
        self.assertContains(response, 'engineer1')
        self.assertContains(response, '40.00%')
        self.assertContains(response, 'Newest inspection')
        self.assertContains(response, 'Newest remarks')
        self.assertNotContains(response, 'Add Inspection')
        self.assertNotContains(response, 'Edit Inspection')

    def test_staff_can_edit_one_inspection_without_changing_another(self):
        first = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date='2026-05-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('20.00'),
            findings='First record',
        )
        second = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date='2026-06-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('40.00'),
            findings='Second record',
        )
        self.client.force_login(self.staff)
        update_url = reverse(
            'engineering_projects:inspection_update',
            args=[self.infrastructure.pk, second.pk],
        )

        response = self.client.post(update_url, {
            'inspection_date': '2026-06-02',
            'completion_percentage': '45.00',
            'findings': 'Second record updated',
            'remarks': 'Updated remarks',
        })

        self.assertRedirects(response, self.detail_url)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.findings, 'First record')
        self.assertEqual(first.completion_percentage, Decimal('20.00'))
        self.assertEqual(second.findings, 'Second record updated')
        self.assertEqual(second.completion_percentage, Decimal('45.00'))

    def test_non_staff_roles_cannot_add_or_edit_inspections(self):
        inspection = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date='2026-06-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('40.00'),
        )
        update_url = reverse(
            'engineering_projects:inspection_update',
            args=[self.infrastructure.pk, inspection.pk],
        )
        inspection.refresh_from_db()
        original = (
            inspection.inspection_date,
            inspection.completion_percentage,
        )

        for user in [self.head, self.mayor_head, self.admin]:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.create_url).status_code, 403)
                self.assertEqual(self.add_inspection(
                    '2026-07-01',
                    '60.00',
                    'Unauthorized inspection',
                ).status_code, 403)
                self.assertEqual(self.client.post(update_url, {
                    'inspection_date': '2026-07-01',
                    'completion_percentage': '60.00',
                    'findings': 'Unauthorized update',
                    'remarks': '',
                }).status_code, 403)

        self.assertEqual(
            self.infrastructure.project.inspections.count(),
            1,
        )
        inspection.refresh_from_db()
        self.assertEqual(
            (inspection.inspection_date, inspection.completion_percentage),
            original,
        )

    def test_multiple_photos_and_pdf_belong_to_one_inspection(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.create_url, {
            'inspection_type': 'progress',
            'inspection_date': '2026-07-01',
            'completion_percentage': '60.00',
            'findings': 'Evidence recorded',
            'remarks': '',
            'inspection_photos': [
                SimpleUploadedFile(
                    'north.jpg',
                    b'north-photo',
                    content_type='image/jpeg',
                ),
                SimpleUploadedFile(
                    'south.png',
                    b'south-photo',
                    content_type='image/png',
                ),
            ],
            'inspection_documents': [SimpleUploadedFile(
                'inspection-report.pdf',
                b'%PDF-1.4 inspection report',
                content_type='application/pdf',
            )],
        })

        self.assertRedirects(response, self.detail_url)
        inspection = self.infrastructure.project.inspections.get()
        self.assertEqual(inspection.inspection_type, 'progress')
        self.assertEqual(inspection.evidence.count(), 3)
        self.assertEqual(
            inspection.evidence.filter(evidence_type='image').count(),
            2,
        )
        self.assertEqual(
            inspection.evidence.filter(evidence_type='document').count(),
            1,
        )
        self.assertTrue(all(
            item.uploaded_by_user == self.staff
            for item in inspection.evidence.all()
        ))
        self.assertTrue(all(
            default_storage.exists(item.storage_name)
            for item in inspection.evidence.all()
        ))

        self.client.force_login(self.head)
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, 'Progress')
        self.assertContains(detail, 'north.jpg')
        self.assertContains(detail, 'south.png')
        self.assertContains(detail, 'inspection-report.pdf')
        self.assertContains(detail, 'Supporting Evidence')
        self.assertContains(detail, 'class="evidence-photo-card"', count=2)
        self.assertContains(detail, 'class="evidence-document-card"')
        self.assertNotContains(detail, 'Remove Existing Evidence')

    def test_staff_can_remove_and_add_evidence_while_editing(self):
        inspection = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_type='routine',
            inspection_date='2026-07-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('60.00'),
        )
        first = InspectionEvidence.objects.create(
            inspection=inspection,
            evidence_type='image',
            original_name='remove.jpg',
            storage_name=default_storage.save(
                'inspections/test/remove.jpg',
                SimpleUploadedFile('remove.jpg', b'remove'),
            ),
            file_url='/media/inspections/test/remove.jpg',
            content_type='image/jpeg',
            uploaded_by_user=self.staff,
        )
        retained = InspectionEvidence.objects.create(
            inspection=inspection,
            evidence_type='document',
            original_name='retain.pdf',
            storage_name=default_storage.save(
                'inspections/test/retain.pdf',
                SimpleUploadedFile('retain.pdf', b'retain'),
            ),
            file_url='/media/inspections/test/retain.pdf',
            content_type='application/pdf',
            uploaded_by_user=self.staff,
        )
        removed_storage_name = first.storage_name
        update_url = reverse(
            'engineering_projects:inspection_update',
            args=[self.infrastructure.pk, inspection.pk],
        )
        self.client.force_login(self.staff)

        response = self.client.post(update_url, {
            'inspection_type': 'routine',
            'inspection_date': '2026-07-01',
            'completion_percentage': '60.00',
            'findings': '',
            'remarks': '',
            'evidence_to_remove': [str(first.pk)],
            'inspection_photos': [SimpleUploadedFile(
                'replacement.webp',
                b'replacement',
                content_type='image/webp',
            )],
        })

        self.assertRedirects(response, self.detail_url)
        self.assertFalse(
            InspectionEvidence.objects.filter(pk=first.pk).exists(),
        )
        self.assertFalse(default_storage.exists(removed_storage_name))
        self.assertTrue(
            InspectionEvidence.objects.filter(pk=retained.pk).exists(),
        )
        self.assertTrue(inspection.evidence.filter(
            original_name='replacement.webp',
        ).exists())

    def test_invalid_evidence_types_are_rejected(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.create_url, {
            'inspection_type': 'routine',
            'inspection_date': '2026-07-01',
            'completion_percentage': '60.00',
            'findings': '',
            'remarks': '',
            'inspection_photos': [SimpleUploadedFile(
                'malware.exe',
                b'not-an-image',
                content_type='application/octet-stream',
            )],
            'inspection_documents': [SimpleUploadedFile(
                'notes.txt',
                b'not-a-pdf',
                content_type='text/plain',
            )],
        })

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            'unsupported file type',
            count=2,
            status_code=400,
        )
        self.assertFalse(self.infrastructure.project.inspections.exists())

    def test_existing_inspection_without_evidence_displays_normally(self):
        inspection = Project_Inspection.objects.create(
            project=self.infrastructure.project,
            inspection_date='2026-07-01',
            inspected_by_user=self.staff,
            completion_percentage=Decimal('60.00'),
        )
        self.assertEqual(inspection.inspection_type, 'routine')
        self.client.force_login(self.head)

        response = self.client.get(self.detail_url)

        self.assertContains(response, 'Routine')
        self.assertContains(response, 'No supporting evidence attached.')

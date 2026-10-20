from copy import deepcopy

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from apps.non_infrastructure import tests as fixtures
from apps.non_infrastructure.forms import NonInfrastructureProjectForm
from apps.system.models import ProjectRevision, UserRole
from apps.system.publication_diff import compare_snapshots
from apps.system.publication_snapshots import build_project_publication_snapshot


class BeneficiarySponsorTests(TestCase):
    training_form = fixtures.NonInfrastructureProjectFormTests.training_form

    def setUp(self):
        fixtures.NonInfrastructureProjectFormTests.setUp(self)

    def create(self, **values):
        form = self.training_form(**values)
        self.assertTrue(form.is_valid(), form.errors)
        return form.save(user=self.user)

    def test_create_free_form_beneficiary_and_optional_sponsor(self):
        project = self.create(target_beneficiaries='Local farming cooperatives', sponsored_by='Community Foundation')
        self.assertEqual(project.target_beneficiaries, 'Local farming cooperatives')
        self.assertEqual(project.sponsored_by, 'Community Foundation')

    def test_blank_sponsor_is_allowed_and_stored_cleanly(self):
        project = self.create(sponsored_by='   ')
        self.assertEqual(project.sponsored_by, '')

    def test_edit_can_clear_sponsor_without_changing_beneficiary_type(self):
        project = self.create(sponsored_by='Initial Sponsor')
        form = NonInfrastructureProjectForm(data=self.training_form(sponsored_by='').data, instance=project)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(user=self.user, instance=project)
        self.assertEqual(saved.sponsored_by, '')
        self.assertEqual(saved.target_beneficiaries, 'Community health volunteers')

    def test_edit_populates_and_updates_existing_fields_without_duplicate_data(self):
        project = self.create(sponsored_by='Initial Sponsor')
        initial = NonInfrastructureProjectForm(instance=project)
        self.assertEqual(initial['sponsored_by'].value(), 'Initial Sponsor')
        data = self.training_form(target_beneficiaries='Youth associations', sponsored_by='New Sponsor').data
        form = NonInfrastructureProjectForm(data=data, instance=project)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(user=self.user, instance=project)
        self.assertEqual(saved.pk, project.pk)
        self.assertEqual(saved.target_beneficiaries, 'Youth associations')
        self.assertEqual(saved.sponsored_by, 'New Sponsor')

    def test_event_beneficiary_type_is_available_without_training_only_requirement(self):
        form = self.training_form(project_type='EVENT', event_date='2026-08-01', start_time='08:00', end_time='09:00', target_beneficiaries='')
        self.assertTrue(form.is_valid(), form.errors)
        html = render_to_string('non_infrastructure/non_infrastructure_form.html', {'form': form, 'action': 'Create'})
        self.assertIn('Beneficiary Type', html)
        self.assertIn('Sponsored By', html)
        self.assertIn('Optional organization', html)
        self.assertNotIn('data-project-types="PROGRAM SERVICE TRAINING CAMPAIGN"', html)

    def test_details_and_frozen_public_snapshot_keep_unpublished_changes_hidden(self):
        project = self.create(target_beneficiaries='Farmers', sponsored_by='Published Sponsor')
        UserRole.objects.create(user=self.user, department='mayor', role='staff')
        self.client.force_login(self.user)
        internal = self.client.get(reverse('mayor_projects:non_infrastructure_project_detail', args=[project.pk]))
        self.assertContains(internal, 'Published Sponsor')
        self.assertContains(internal, 'Beneficiary Type')
        revision = ProjectRevision.objects.create(
            project=project.project, revision_number=1, status='published', is_current_public=True,
            snapshot=build_project_publication_snapshot(project.project),
        )
        original = deepcopy(revision.snapshot)
        project.sponsored_by = 'Private Draft Sponsor'
        project.target_beneficiaries = 'Unpublished Group'
        project.save()
        self.client.logout()
        response = self.client.get(reverse('public_non_infrastructure_project_detail', args=[project.pk]))
        self.assertContains(response, 'Published Sponsor')
        self.assertContains(response, 'Farmers')
        self.assertNotContains(response, 'Private Draft Sponsor')
        self.assertNotContains(response, 'Unpublished Group')
        revision.refresh_from_db()
        self.assertEqual(revision.snapshot, original)

    def test_review_comparison_labels_both_fields(self):
        project = self.create(target_beneficiaries='Farmers', sponsored_by='Foundation')
        snapshot = build_project_publication_snapshot(project.project)
        comparison = compare_snapshots(snapshot)
        rows = [row for section in comparison['sections'] for row in section['fields']]
        labels = {row['label'] for row in rows}
        self.assertIn('Beneficiary Type', labels)
        self.assertIn('Sponsored By', labels)

    def test_existing_snapshot_without_sponsor_remains_readable(self):
        project = self.create()
        snapshot = build_project_publication_snapshot(project.project)
        snapshot['non_infrastructure'].pop('sponsored_by')
        ProjectRevision.objects.create(project=project.project, revision_number=1, status='published', is_current_public=True, snapshot=snapshot)
        response = self.client.get(reverse('public_non_infrastructure_project_detail', args=[project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Sponsored By')

from copy import deepcopy

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from apps.non_infrastructure import tests as fixtures
from apps.non_infrastructure.forms import NonInfrastructureProjectForm
from apps.system.models import NonInfrastructureProject, ProjectRevision, UserRole
from apps.system.publication_diff import compare_snapshots
from apps.system.publication_snapshots import build_project_publication_snapshot
from apps.system.publication_service import (
    confirm_head_operational_information, publish_publication_revision,
    review_publication_revision, submit_project_for_review,
)


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

    def test_simplified_form_exposes_only_requested_additions(self):
        form = self.training_form(target_beneficiaries='')
        self.assertTrue(form.is_valid(), form.errors)
        html = render_to_string('non_infrastructure/non_infrastructure_form.html', {'form': form, 'action': 'Create'})
        self.assertIn('Beneficiary Type', html)
        self.assertIn('Sponsored By', html)
        self.assertIn('Optional organization', html)
        self.assertNotIn('data-project-types', html)
        self.assertNotIn('Project Type', html)
        self.assertNotIn('Event Date', html)
        self.assertNotIn('project_type', form.fields)
        self.assertNotIn('event_date', form.fields)
        self.assertTrue(form.fields['implementation_start_date'].required)
        self.assertTrue(form.fields['implementation_end_date'].required)

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

    def test_create_return_correct_approve_publish_preserves_both_fields(self):
        UserRole.objects.create(user=self.user, department='mayor', role='staff')
        head = get_user_model().objects.create_user('beneficiary-review-head', is_staff=True)
        UserRole.objects.create(user=head, department='mayor', role='head')
        self.client.force_login(self.user)
        payload = self.training_form(
            target_beneficiaries='Farmer cooperatives', sponsored_by='Initial Foundation',
        ).data.copy()
        self.assertEqual(self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_create',
        ), payload).status_code, 302)
        project = NonInfrastructureProject.objects.get(project__created_by_user=self.user)
        submit_url = reverse('mayor_projects:non_infrastructure_project_submit_for_review', args=[project.pk])
        self.assertEqual(self.client.post(submit_url).status_code, 302)
        revision = project.project.revisions.latest('revision_number')
        self.assertEqual(revision.status, 'pending_review')
        self.client.force_login(head)
        review_url = reverse('publication_revision_review', args=[revision.pk])
        review = self.client.get(reverse('publication_revision_detail', args=[revision.pk]))
        self.assertContains(review, 'Farmer cooperatives')
        self.assertContains(review, 'Initial Foundation')
        self.assertEqual(self.client.post(review_url, {
            'decision': 'needs_revision', 'notes': 'Correct the beneficiary group and sponsor.',
        }).status_code, 302)
        self.client.force_login(self.user)
        payload.update(target_beneficiaries='Barangay farmer cooperatives', sponsored_by='Corrected Foundation')
        self.assertEqual(self.client.post(reverse(
            'mayor_projects:non_infrastructure_project_update', args=[project.pk],
        ), payload).status_code, 302)
        self.assertEqual(self.client.post(submit_url).status_code, 302)
        revision = project.project.revisions.latest('revision_number')
        self.client.force_login(head)
        self.assertEqual(self.client.post(reverse('publication_revision_review', args=[revision.pk]), {
            'decision': 'approved',
        }).status_code, 302)
        confirm_head_operational_information(revision, head)
        revision.refresh_from_db()
        retained = deepcopy(revision.snapshot)
        self.assertEqual(retained['non_infrastructure']['target_beneficiaries'], 'Barangay farmer cooperatives')
        self.assertEqual(retained['non_infrastructure']['sponsored_by'], 'Corrected Foundation')
        self.assertEqual(self.client.post(reverse('publication_revision_publish', args=[revision.pk])).status_code, 302)
        self.client.logout()
        public_url = reverse('public_non_infrastructure_project_detail', args=[project.pk])
        self.assertContains(self.client.get(public_url), 'Corrected Foundation')
        project.sponsored_by = 'Unpublished Sponsor'
        project.target_beneficiaries = 'Unpublished Beneficiaries'
        project.save()
        self.assertNotContains(self.client.get(public_url), 'Unpublished Sponsor')
        self.assertNotContains(self.client.get(public_url), 'Unpublished Beneficiaries')
        revision.refresh_from_db()
        self.assertEqual(revision.snapshot, retained)

    def test_simplified_form_preserves_non_rendered_existing_values_on_edit(self):
        project = self.create()
        project.project_cost = 12345
        project.contractor_supplier = 'Retained legacy supplier'
        project.remarks = 'Retained legacy remarks'
        project.save()
        data = self.training_form(target_beneficiaries='Youth associations', sponsored_by='Foundation').data.copy()
        form = NonInfrastructureProjectForm(data=data, instance=project)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(user=self.user, instance=project)
        self.assertEqual(saved.project_cost, 12345)
        self.assertEqual(saved.contractor_supplier, 'Retained legacy supplier')
        self.assertEqual(saved.remarks, 'Retained legacy remarks')

    def test_blank_sponsor_and_beneficiary_group_do_not_block_publication(self):
        project = self.create(target_beneficiaries='', sponsored_by='')
        UserRole.objects.create(user=self.user, department='mayor', role='staff')
        head = get_user_model().objects.create_user('blank-sponsor-review-head', is_staff=True)
        UserRole.objects.create(user=head, department='mayor', role='head')
        revision = submit_project_for_review(project.project, self.user)
        revision = review_publication_revision(revision, head, 'approved')
        confirm_head_operational_information(revision, head)
        revision = publish_publication_revision(revision, head)
        self.assertEqual(revision.snapshot['non_infrastructure']['sponsored_by'], '')
        self.assertEqual(revision.snapshot['non_infrastructure']['target_beneficiaries'], '')
        self.assertEqual(revision.status, 'published')
        response = self.client.get(reverse('public_non_infrastructure_project_detail', args=[project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Sponsored By')

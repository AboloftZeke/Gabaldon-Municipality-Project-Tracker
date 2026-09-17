"""Fresh-schema and normalized UI regression checks."""
import re

from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from .models import (Address, InfrastructureProject, NonInfrastructureCategory,
                     NonInfrastructureProject, Project, ProjectImage, UserRole)


class CleanSchemaTests(TestCase):
    def test_only_current_models_and_tables_exist(self):
        from verify_schema import verify_schema
        tables = verify_schema()
        self.assertTrue(all(re.fullmatch(r'system_[a-z_]+', table) for table in tables))
        models = list(apps.get_app_config('system').get_models())
        self.assertTrue(all(model._meta.managed for model in models))
        self.assertEqual(len({model._meta.db_table for model in models}), len(models))
        self.assertFalse(list(apps.get_app_config('infrastructure').get_models()))
        self.assertFalse(list(apps.get_app_config('non_infrastructure').get_models()))
        self.assertNotIn('system_legacy_userprofile_archive', tables)
        for name in ['auth_user', 'django_content_type', 'django_session', 'django_admin_log', 'django_migrations']:
            self.assertIn(name, connection.introspection.table_names())

    def test_migrated_schema_uses_clean_columns_and_relations(self):
        from .models import ProjectRevision
        self.assertEqual(InfrastructureProject._meta.get_field('title').column, 'title')
        self.assertEqual(NonInfrastructureProject._meta.get_field('category').column, 'category_id')
        self.assertEqual(ProjectRevision._meta.get_field('previous_revision').column, 'previous_revision_id')
        self.assertEqual(ProjectRevision._meta.get_field('project').remote_field.related_name, 'revisions')
        self.assertFalse(hasattr(User, 'profile'))

    def test_non_infrastructure_list_renders_relations_cover_and_official_status(self):
        user = User.objects.create_user('schema-mayor', is_staff=True)
        UserRole.objects.create(user=user, department='mayor', role='staff')
        self.client.force_login(user)
        category = NonInfrastructureCategory.objects.get(type_code='health_support')
        project = Project.objects.create(project_type='non_infrastructure', created_by_user=user)
        record = NonInfrastructureProject.objects.create(
            project=project, title='Normalized health program', category=category,
            address=Address.objects.create(barangay='Bagting'), status='ongoing',
        )
        ProjectImage.objects.create(project=project, image_url='/media/chosen-cover.jpg', is_cover=True)
        ProjectImage.objects.create(project=project, image_url='/media/newer-image.jpg')
        response = self.client.get(reverse('mayor_projects:non_infrastructure_project_list'),
                                   {'category': category.pk, 'location': 'Bagting'})
        for value in [record.title, 'Bagting', 'Health Support', 'Ongoing', '/media/chosen-cover.jpg']:
            self.assertContains(response, value)
        self.assertNotContains(response, '/media/newer-image.jpg')

    def test_new_projects_are_not_implicitly_published(self):
        project = Project.objects.create(project_type='infrastructure')
        InfrastructureProject.objects.create(project=project, title='Working copy')
        self.assertFalse(project.is_published)
        self.assertFalse(project.is_visible_to_public)
        self.assertFalse(project.revisions.exists())

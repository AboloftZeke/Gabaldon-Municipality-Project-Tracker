from django.test import TestCase

from apps.non_infrastructure.forms import NonInfrastructureProjectForm


class NonInfrastructureProjectFormTests(TestCase):
    def test_form_accepts_instance_keyword(self):
        form = NonInfrastructureProjectForm(instance=object())
        self.assertIsNotNone(form)
        self.assertIsNotNone(form.instance)

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.system.models import (
    InfrastructureProject,
    NonInfrastructureProject,
    Project,
)
from apps.system.permissions import (
    can_update_infrastructure_operations,
    can_update_non_infrastructure_operations,
)
from apps.system.status_transitions import is_valid_project_status_transition


class ProjectCompletionConfirmationView(
    LoginRequiredMixin,
    UserPassesTestMixin,
    View,
):
    """Apply a Head's explicit decision to a project at full completion."""

    login_url = 'login'
    project_type = None

    def _details_model(self):
        return {
            'infrastructure': InfrastructureProject,
            'non_infrastructure': NonInfrastructureProject,
        }.get(self.project_type)

    def test_func(self):
        model = self._details_model()
        project_details = (
            model.objects.select_related('project').filter(
                pk=self.kwargs['pk'],
            ).first()
            if model is not None
            else None
        )
        if (
            project_details is None
            or project_details.project.project_type != self.project_type
        ):
            return False
        if self.project_type == 'infrastructure':
            return can_update_infrastructure_operations(self.request.user)
        if self.project_type == 'non_infrastructure':
            return can_update_non_infrastructure_operations(self.request.user)
        return False

    def _project_details(self, pk, *, lock=False):
        model = self._details_model()
        queryset = model.objects
        if lock:
            queryset = queryset.select_for_update()
        return get_object_or_404(queryset, pk=pk)

    def _success_url(self, project_details):
        if self.project_type == 'infrastructure':
            return redirect(
                'engineering_projects:project_detail',
                pk=project_details.pk,
            )
        return redirect(
            'mayor_projects:non_infrastructure_project_detail',
            pk=project_details.pk,
        )

    @transaction.atomic
    def post(self, request, pk):
        project_id = self._project_details(pk).project_id
        project = get_object_or_404(
            Project.objects.select_for_update(),
            pk=project_id,
            project_type=self.project_type,
        )
        project_details = self._project_details(pk, lock=True)
        decision = request.POST.get('decision')
        if decision not in {'yes', 'no'}:
            messages.error(request, 'Choose whether to mark the project Completed.')
            return self._success_url(project_details)
        if (
            project.completion_confirmation_status
            != Project.CompletionConfirmationStatus.PENDING
        ):
            messages.info(request, 'This completion confirmation was already addressed.')
            return self._success_url(project_details)
        if project_details.status == 'completed':
            project.completion_confirmation_status = ''
            project.save(update_fields=[
                'completion_confirmation_status',
                'updated_at',
            ])
            messages.info(request, 'The project is already Completed.')
            return self._success_url(project_details)
        if project.completion_percentage is None or project.completion_percentage < 100:
            messages.error(
                request,
                'The project must have 100% recorded completion before its status can be confirmed.',
            )
            return self._success_url(project_details)
        if decision == 'no':
            project.completion_confirmation_status = (
                Project.CompletionConfirmationStatus.DECLINED
            )
            project.save(update_fields=[
                'completion_confirmation_status',
                'updated_at',
            ])
            messages.info(
                request,
                'The project remains at 100% completion and its status was not changed.',
            )
            return self._success_url(project_details)

        if (
            self.project_type == 'infrastructure'
            and not is_valid_project_status_transition(
                project_details.status,
                'completed',
            )
        ):
            messages.error(
                request,
                'The project status cannot be changed to Completed from its current status.',
            )
            return self._success_url(project_details)

        project_details.status = 'completed'
        project_details.save(update_fields=['status', 'updated_at'])
        project.completion_confirmation_status = ''
        project.save(update_fields=[
            'completion_confirmation_status',
            'updated_at',
        ])
        messages.success(request, 'Project status updated to Completed.')
        return self._success_url(project_details)

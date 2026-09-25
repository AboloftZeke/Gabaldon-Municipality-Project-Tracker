from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.core.exceptions import SuspiciousFileOperation, ValidationError
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, FormView
from django.urls import reverse_lazy, reverse, NoReverseMatch
from django.db import models, transaction
from django.db.models import Prefetch, Q, Sum
from django.templatetags.static import static
from django.utils import timezone
from .forms import NonInfrastructureOperationalForm, NonInfrastructureProgressReturnForm, NonInfrastructureProgressUpdateForm, NonInfrastructureProjectForm
from .progress_application import apply_approved_progress_update
from apps.system.models import NonInfrastructureCategory, NonInfrastructureProgressUpdate, NonInfrastructureProject, Project, ProjectImage
from apps.system.publication_service import (
    create_head_operational_revision,
    publication_state,
    submit_project_for_review,
)


from apps.system.permissions import (
    can_manage_non_infrastructure,
    can_update_non_infrastructure_operations,
    department_for_user as _department_for_user,
    is_system_admin,
)


class MayorsOfficeOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow only Mayor's Office users, explicitly exclude admins"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        return can_manage_non_infrastructure(self.request.user)


class MayorHeadOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        return can_update_non_infrastructure_operations(self.request.user)


class MayorsOfficeRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow only Mayor's Office users and admins"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        if is_system_admin(self.request.user):
            return True
        department = _department_for_user(self.request.user)
        return department == 'mayor'


class MayorsOfficeEditMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow Mayor's Office and admins to edit, prevent engineering office"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        return (
            is_system_admin(self.request.user)
            or can_manage_non_infrastructure(self.request.user)
        )

    def get_namespaced_url(self, url_name, *args, **kwargs):
        """
        Resolve a URL name within the current resolver match namespace.
        Falls back to un-namespaced resolution if namespace resolution fails.
        """
        namespace = self.request.resolver_match.namespace
        if namespace:
            try:
                return reverse(f"{namespace}:{url_name}", args=args, kwargs=kwargs)
            except NoReverseMatch:
                pass
        try:
            return reverse(url_name, args=args, kwargs=kwargs)
        except NoReverseMatch:
            return "/"


class NonInfrastructureProjectDashboardView(MayorsOfficeRequiredMixin, TemplateView):
        """Dashboard for Mayor's Office to manage non-infrastructure projects"""
        template_name = 'non_infrastructure/non_infrastructure_dashboard.html'

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)

            # All Mayor's Office users see the same project pool using the normalized model.
            user_projects = NonInfrastructureProject.objects.select_related('project', 'address', 'category').prefetch_related(Prefetch('project__images', queryset=ProjectImage.objects.order_by('-is_cover', '-created_at')))

            context['total_projects'] = user_projects.count()

            context['planned_projects'] = user_projects.filter(status='planned').count()
            context['in_progress_projects'] = user_projects.filter(status='ongoing').count()
            context['completed_projects'] = user_projects.filter(status='completed').count()

            context['recent_projects'] = user_projects.order_by('-created_at')[:5]

            return context


class NonInfrastructureProjectListView(MayorsOfficeRequiredMixin, ListView):
    """Display list of non-infrastructure projects"""
    model = NonInfrastructureProject
    template_name = 'non_infrastructure/non_infrastructure_list.html'
    context_object_name = 'projects'
    paginate_by = 10

    def get_queryset(self):
        queryset = NonInfrastructureProject.objects.select_related('project', 'address', 'category').prefetch_related(Prefetch('project__images', queryset=ProjectImage.objects.order_by('-is_cover', '-created_at')))

        # Filter by location
        location = self.request.GET.get('location', '').strip()
        if location:
            queryset = queryset.filter(address__barangay=location)

        # Filter by category
        category = self.request.GET.get('category', '').strip()
        if category:
            queryset = queryset.filter(category_id=category)

        project_type = self.request.GET.get('project_type', '').strip()
        if project_type:
            queryset = queryset.filter(project_type=project_type)

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for project in context['projects']:
            project.publication_state = publication_state(project.project)
        context['locations'] = NonInfrastructureProject.objects.values_list('address__barangay', flat=True).distinct()
        context['categories'] = NonInfrastructureCategory.objects.all()
        context['project_types'] = NonInfrastructureProject.ProjectType.choices
        context['has_any_projects'] = NonInfrastructureProject.objects.exists()
        context['has_active_filters'] = any(
            self.request.GET.get(name, '').strip()
            for name in ('location', 'category', 'project_type')
        )
        context['can_update_operations'] = (
            can_update_non_infrastructure_operations(self.request.user)
        )
        return context


class NonInfrastructureProjectCreateView(MayorsOfficeOnlyMixin, CreateView):
    """Create a new non-infrastructure project - Mayor's Office only"""
    model = NonInfrastructureProject
    form_class = NonInfrastructureProjectForm
    template_name = 'non_infrastructure/non_infrastructure_form.html'

    def get_success_url(self):
        return reverse('mayor_projects:non_infrastructure_project_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Create'
        return context

    def form_valid(self, form):
        non = form.save(user=self.request.user)
        self.object = non
        return redirect(self.get_success_url())


class NonInfrastructureProjectDetailView(MayorsOfficeRequiredMixin, DetailView):
    """Display project details"""
    model = NonInfrastructureProject
    template_name = 'non_infrastructure/non_infrastructure_detail.html'
    context_object_name = 'project'

    def get_queryset(self):
        return NonInfrastructureProject.objects.select_related('project', 'address', 'category').prefetch_related(Prefetch('project__images', queryset=ProjectImage.objects.order_by('-is_cover', '-created_at')))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project_record = self.object
        normalized = project_record
        project = project_record

        project_name = (
            getattr(project, 'title', '')
            or 'Non-Infrastructure Project'
        )

        creator = (
            getattr(project.project, 'created_by_user', None)
            if getattr(project, 'project', None)
            else None
        )

        project_manager = (
            creator.get_full_name() or creator.username
            if creator
            else 'N/A'
        )

        project_images = []

        if getattr(project, 'project', None):
            project_images = list(
                project.project.images.order_by('-is_cover', '-created_at')
            )

        context['project_code'] = f'NINF-{project_record.pk:05d}'
        context['project_type_label'] = project.get_project_type_display()
        context['project_name'] = project_name
        context['project_manager'] = project_manager

        context['project_status'] = project.get_status_display()
        context['project_category'] = (
            getattr(
                getattr(project, 'category', None),
                'type_name',
                ''
            )
        )

        context['project_description'] = (
            getattr(project, 'description', '') or ''
        )

        context['project_proponent'] = (
            getattr(project, 'proponent', '') or ''
        )

        context['project_beneficiaries'] = getattr(
            project,
            'beneficiaries',
            None
        )
        context['project_target_beneficiaries'] = project.target_beneficiaries or ''
        context['project_implementation_start'] = project.implementation_start_date
        context['project_implementation_end'] = project.implementation_end_date
        context['project_cost'] = project.project_cost
        context['project_fund_source'] = project.fund_source or ''
        context['project_contractor_supplier'] = project.contractor_supplier or ''
        context['project_procurement_description'] = project.procurement_description or ''
        context['project_quantity'] = project.quantity
        context['project_expected_delivery_date'] = project.expected_delivery_date
        context['project_remarks'] = project.remarks or ''

        context['project_event_date'] = getattr(
            project,
            'event_date',
            None
        )

        context['project_start_time'] = getattr(
            project,
            'start_time',
            None
        )

        context['project_end_time'] = getattr(
            project,
            'end_time',
            None
        )

        context['project_venue'] = (
            getattr(project, 'venue_name', '') or ''
        )

        context['project_address'] = getattr(
            project,
            'address',
            None
        )

        context['project_images'] = project_images
        context['can_update_operations'] = (
            can_update_non_infrastructure_operations(self.request.user)
        )
        context['can_manage_project'] = (
            is_system_admin(self.request.user)
            or can_manage_non_infrastructure(self.request.user)
        )
        context['can_create_progress_update'] = can_manage_non_infrastructure(self.request.user)
        if context['can_create_progress_update']:
            context['staff_progress_updates'] = project.progress_updates.filter(
                submitted_by=self.request.user,
            ).order_by('-created_at', '-progress_update_id')

        context['project_placeholder_image'] = static(
            'images/project-placeholder.svg'
        )

        if normalized and normalized.project:
            context['publication'] = publication_state(normalized.project)
            context['publication_submit_url'] = reverse(
                'mayor_projects:non_infrastructure_project_submit_for_review',
                args=[project_record.pk],
            )
            context['can_manage_publication'] = can_manage_non_infrastructure(self.request.user)

        return context


class NonInfrastructureProgressUpdateCreateView(MayorsOfficeOnlyMixin, FormView):
    """Let Mayor's Office Staff save a proposed update as a private draft."""

    form_class = NonInfrastructureProgressUpdateForm
    template_name = 'non_infrastructure/non_infrastructure_progress_update_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(NonInfrastructureProject, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = self.project
        return context

    def form_valid(self, form):
        try:
            update = form.save(project=self.project, user=self.request.user)
        except (OSError, SuspiciousFileOperation):
            form.add_error('evidence_files', 'The file could not be saved. Please try again.')
            return self.form_invalid(form)
        messages.success(self.request, 'Project update saved as a draft.')
        return redirect(
            'mayor_projects:non_infrastructure_progress_update_detail',
            pk=self.project.pk,
            update_pk=update.pk,
        )


class NonInfrastructureProgressUpdateDetailView(MayorsOfficeOnlyMixin, DetailView):
    """Show a staff member only their own saved progress updates."""

    model = NonInfrastructureProgressUpdate
    pk_url_kwarg = 'update_pk'
    context_object_name = 'progress_update'
    template_name = 'non_infrastructure/non_infrastructure_progress_update_detail.html'

    def get_queryset(self):
        return NonInfrastructureProgressUpdate.objects.filter(
            non_infrastructure_id=self.kwargs['pk'],
            submitted_by=self.request.user,
        ).select_related('non_infrastructure').prefetch_related('evidence')


class NonInfrastructureProgressUpdateSubmitView(MayorsOfficeOnlyMixin, View):
    """Move an owned draft with evidence to pending review exactly once."""

    http_method_names = ['post']

    def post(self, request, pk, update_pk):
        with transaction.atomic():
            update = get_object_or_404(
                NonInfrastructureProgressUpdate.objects.select_for_update(),
                pk=update_pk,
                non_infrastructure_id=pk,
                submitted_by=request.user,
            )
            if update.review_status != NonInfrastructureProgressUpdate.ReviewStatus.DRAFT:
                messages.error(request, 'Only Draft updates can be submitted for review.')
            elif (
                update.proposed_status not in dict(NonInfrastructureProject.STATUS_CHOICES)
                or not update.remarks.strip()
            ):
                messages.error(request, 'Add a valid proposed status and remarks before submitting.')
            elif not update.evidence.exists():
                messages.error(request, 'Add supporting evidence before submitting this update.')
            else:
                update.review_status = NonInfrastructureProgressUpdate.ReviewStatus.PENDING_REVIEW
                update.submitted_at = timezone.now()
                update.save(update_fields=['review_status', 'submitted_at', 'updated_at'])
                messages.success(request, 'Progress update submitted for Mayor Head review.')
        return redirect(
            'mayor_projects:non_infrastructure_progress_update_detail',
            pk=pk,
            update_pk=update_pk,
        )


class NonInfrastructureProgressReviewQueueView(MayorHeadOnlyMixin, ListView):
    """List all pending staff progress updates for the Mayor Head."""

    template_name = 'non_infrastructure/non_infrastructure_progress_review_queue.html'
    context_object_name = 'progress_updates'
    paginate_by = 20

    def get_queryset(self):
        return NonInfrastructureProgressUpdate.objects.filter(
            review_status=NonInfrastructureProgressUpdate.ReviewStatus.PENDING_REVIEW,
        ).select_related('non_infrastructure', 'submitted_by').order_by(
            '-submitted_at', '-progress_update_id',
        )


class NonInfrastructureProgressReviewDetailView(MayorHeadOnlyMixin, DetailView):
    """Let the Mayor Head inspect evidence before recording a decision."""

    model = NonInfrastructureProgressUpdate
    pk_url_kwarg = 'update_pk'
    context_object_name = 'progress_update'
    template_name = 'non_infrastructure/non_infrastructure_progress_review_detail.html'

    def get_queryset(self):
        return NonInfrastructureProgressUpdate.objects.select_related(
            'non_infrastructure', 'submitted_by', 'reviewed_by',
        ).prefetch_related('evidence')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['return_form'] = kwargs.get('return_form') or NonInfrastructureProgressReturnForm()
        return context


class NonInfrastructureProgressReviewDecisionView(MayorHeadOnlyMixin, View):
    """Lock a pending update and record exactly one Head review decision."""

    http_method_names = ['post']
    decision = None

    def post(self, request, update_pk):
        with transaction.atomic():
            update = get_object_or_404(
                NonInfrastructureProgressUpdate.objects.select_for_update().prefetch_related('evidence'),
                pk=update_pk,
            )
            if update.review_status != NonInfrastructureProgressUpdate.ReviewStatus.PENDING_REVIEW:
                messages.error(request, 'Only Pending Review updates can be reviewed.')
                return redirect('mayor_projects:non_infrastructure_progress_review_detail', update_pk=update_pk)

            notes = ''
            if self.decision == NonInfrastructureProgressUpdate.ReviewStatus.RETURNED:
                form = NonInfrastructureProgressReturnForm(request.POST)
                if not form.is_valid():
                    return render(request, 'non_infrastructure/non_infrastructure_progress_review_detail.html', {
                        'progress_update': update,
                        'return_form': form,
                    }, status=400)
                notes = form.cleaned_data['review_notes']
            elif not update.evidence.exists():
                messages.error(request, 'A progress update needs supporting evidence before approval.')
                return redirect('mayor_projects:non_infrastructure_progress_review_detail', update_pk=update_pk)

            update.review_status = self.decision
            update.review_notes = notes
            update.reviewed_by = request.user
            update.reviewed_at = timezone.now()
            update.save(update_fields=[
                'review_status', 'review_notes', 'reviewed_by', 'reviewed_at', 'updated_at',
            ])
            messages.success(request, f'Progress update {update.get_review_status_display().lower()}.')
        return redirect('mayor_projects:non_infrastructure_progress_review_detail', update_pk=update_pk)


class NonInfrastructureProgressApproveView(NonInfrastructureProgressReviewDecisionView):
    decision = NonInfrastructureProgressUpdate.ReviewStatus.APPROVED


class NonInfrastructureProgressReturnView(NonInfrastructureProgressReviewDecisionView):
    decision = NonInfrastructureProgressUpdate.ReviewStatus.RETURNED


class NonInfrastructureProgressApplyView(MayorHeadOnlyMixin, View):
    """Apply a Head-approved update to the working status and create a revision."""

    http_method_names = ['post']

    def post(self, request, update_pk):
        get_object_or_404(NonInfrastructureProgressUpdate, pk=update_pk)
        try:
            update = apply_approved_progress_update(update_pk, request.user)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return redirect('mayor_projects:non_infrastructure_progress_review_detail', update_pk=update_pk)
        messages.success(request, 'Approved status applied. The publication revision is ready for review.')
        return redirect('publication_revision_detail', revision_id=update.publication_revision_id)


class NonInfrastructureOperationalUpdateView(MayorHeadOnlyMixin, UpdateView):
    model = NonInfrastructureProject
    form_class = NonInfrastructureOperationalForm
    template_name = 'non_infrastructure/non_infrastructure_operational_form.html'

    def get_queryset(self):
        return NonInfrastructureProject.objects.select_related('project', 'address', 'category').prefetch_related(Prefetch('project__images', queryset=ProjectImage.objects.order_by('-is_cover', '-created_at')))

    def return_revision(self):
        revision_id = (
            self.request.POST.get('from_review')
            or self.request.GET.get('from_review')
        )
        if not revision_id:
            return None
        return self.object.project.revisions.filter(
            pk=revision_id,
        ).first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return_revision = self.return_revision()
        revision_snapshot = (
            (return_revision.snapshot or {}).get(
                'non_infrastructure',
            ) or {}
            if return_revision else {}
        )
        context['operational_display_title'] = (
            revision_snapshot.get('title') or self.object.title
        )
        context['return_revision_id'] = getattr(
            return_revision,
            'pk',
            None,
        )
        return context

    def get_success_url(self):
        return_revision_id = getattr(self.return_revision(), 'pk', None)
        if return_revision_id:
            return reverse(
                'publication_revision_detail',
                args=[return_revision_id],
            )
        return reverse(
            'mayor_projects:non_infrastructure_project_detail',
            args=[self.object.pk],
        )

    def form_valid(self, form):
        try:
            with transaction.atomic():
                Project.objects.select_for_update().get(
                    pk=form.instance.project_id,
                )
                response = super().form_valid(form)
                revision = create_head_operational_revision(
                    self.object.project,
                    self.request.user,
                )
        except ValidationError as exc:
            form.instance.refresh_from_db()
            form.add_error(None, '; '.join(exc.messages))
            return self.form_invalid(form)
        messages.success(self.request, 'Official project status updated.')
        if revision is not None:
            messages.info(
                self.request,
                f'Revision {revision.revision_number} is approved and awaiting publication.',
            )
            return redirect(
                'publication_revision_detail',
                revision_id=revision.pk,
            )
        return response


class NonInfrastructureProjectSubmitForReviewView(
    MayorsOfficeOnlyMixin,
    View,
):
    """Submit a non-infrastructure working copy for office Head review."""

    def post(self, request, pk):
        non_infrastructure = get_object_or_404(
            NonInfrastructureProject.objects.select_related('project'),
            pk=pk,
        )
        try:
            revision = submit_project_for_review(
                non_infrastructure.project,
                request.user,
            )
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            messages.success(
                request,
                f'Revision {revision.revision_number} was submitted for '
                'office Head review.',
            )
        return redirect(
            'mayor_projects:non_infrastructure_project_detail',
            pk=pk,
        )


class NonInfrastructureProjectEditView(MayorsOfficeEditMixin, UpdateView):
    """Update an existing non-infrastructure project - Mayor's Office and admins only"""
    model = NonInfrastructureProject
    form_class = NonInfrastructureProjectForm
    template_name = 'non_infrastructure/non_infrastructure_form.html'

    def get_success_url(self):
        return reverse('mayor_projects:non_infrastructure_project_list')

    def get_queryset(self):
        return NonInfrastructureProject.objects.select_related('project', 'address', 'category').prefetch_related(Prefetch('project__images', queryset=ProjectImage.objects.order_by('-is_cover', '-created_at')))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Edit'
        return context

    def form_valid(self, form):
        non = form.save(user=self.request.user, instance=self.get_object())
        self.object = non
        return redirect(self.get_success_url())


class NonInfrastructureProjectDeleteView(MayorsOfficeEditMixin, DeleteView):
    """Delete a non-infrastructure project - Mayor's Office and admins only"""
    model = NonInfrastructureProject
    template_name = 'non_infrastructure/non_infrastructure_confirm_delete.html'

    def get_success_url(self):
        return reverse('mayor_projects:non_infrastructure_project_list')

    def get_queryset(self):
        return NonInfrastructureProject.objects.select_related('project', 'address', 'category').prefetch_related(Prefetch('project__images', queryset=ProjectImage.objects.order_by('-is_cover', '-created_at')))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()

        context['cancel_url'] = reverse('mayor_projects:non_infrastructure_project_detail', args=[obj.pk])
        return context

    def form_valid(self, form):
        project_record = self.get_object()
        normalized = (
            NonInfrastructureProject.objects
            .filter(pk=project_record.pk)
            .select_related('project')
            .first()
        )
        if normalized and normalized.project:
            if normalized.project.revisions.exists():
                messages.error(
                    self.request,
                    'A project with publication history cannot be deleted. '
                    'Its publication revisions must remain available as '
                    'historical records.',
                )
                return redirect(
                    'mayor_projects:non_infrastructure_project_detail',
                    pk=project_record.pk,
                )
            normalized.project.delete()
        else:
            project_record.delete()
        return redirect(self.get_success_url())

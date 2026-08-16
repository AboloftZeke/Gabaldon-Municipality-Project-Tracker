from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy, reverse, NoReverseMatch
from django.db import models
from django.db.models import Q, Sum
from django.templatetags.static import static
from django.utils import timezone
from .forms import NonInfrastructureProjectForm
from apps.system.models import NonInfrastructureProject as SystemNonInfrastructureProject
from apps.system.models import Non_Infrastructure_Project, Project, Project_Image


def _department_for_user(user):
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'department', None) if profile is not None else None


class MayorsOfficeOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow only Mayor's Office users, explicitly exclude admins"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        # Explicitly exclude superusers/admins
        if self.request.user.is_superuser:
            return False
        department = _department_for_user(self.request.user)
        return department == 'mayor'


class MayorsOfficeRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow only Mayor's Office users and admins"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        if self.request.user.is_superuser:
            return True
        department = _department_for_user(self.request.user)
        return department == 'mayor'


class MayorsOfficeEditMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow Mayor's Office and admins to edit, prevent engineering office"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        # Allow admins
        if self.request.user.is_superuser:
            return True
        # Allow Mayor's office only, deny engineering office
        department = _department_for_user(self.request.user)
        return department == 'mayor'

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

            # All Mayor's Office users see the same project pool using the normalized compatibility model.
            user_projects = SystemNonInfrastructureProject.objects.all()

            context['total_projects'] = user_projects.count()

            # Non-infrastructure projects no longer have a progress/status field
            # in the redesigned schema, so these cannot be calculated reliably.
            context['planned_projects'] = 0
            context['in_progress_projects'] = 0
            context['completed_projects'] = 0

            context['recent_projects'] = user_projects.order_by('-created_at')[:5]

            return context


class NonInfrastructureProjectListView(MayorsOfficeRequiredMixin, ListView):
    """Display list of non-infrastructure projects"""
    model = SystemNonInfrastructureProject
    template_name = 'non_infrastructure/non_infrastructure_list.html'
    context_object_name = 'projects'
    paginate_by = 10

    def get_queryset(self):
        queryset = SystemNonInfrastructureProject.objects.all()

        # Filter by location
        location = self.request.GET.get('location', '').strip()
        if location:
            queryset = queryset.filter(location=location)

        # Filter by category
        category = self.request.GET.get('category', '').strip()
        if category:
            queryset = queryset.filter(category=category)

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['locations'] = getattr(SystemNonInfrastructureProject, 'LOCATION_CHOICES', [])
        context['categories'] = getattr(SystemNonInfrastructureProject, 'PROJECT_CATEGORY_CHOICES', [])
        return context


class NonInfrastructureProjectCreateView(MayorsOfficeOnlyMixin, CreateView):
    """Create a new non-infrastructure project - Mayor's Office only"""
    model = SystemNonInfrastructureProject
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
        self.object = SystemNonInfrastructureProject.objects.filter(non_infra_name=non.non_infra_name).first()
        return redirect(self.get_success_url())


class NonInfrastructureProjectDetailView(MayorsOfficeRequiredMixin, DetailView):
    """Display project details"""
    model = SystemNonInfrastructureProject
    template_name = 'non_infrastructure/non_infrastructure_detail.html'
    context_object_name = 'project'

    def get_queryset(self):
        return SystemNonInfrastructureProject.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        compat_project = self.object

        normalized = Non_Infrastructure_Project.objects.filter(
            non_infra_id=compat_project.non_infra_id
        ).select_related(
            'project',
            'project__created_by_user',
            'address',
            'non_infra_category',
        ).first()

        project = normalized if normalized is not None else compat_project
        project_name = getattr(project, 'non_infra_name', '') or 'Non-Infrastructure Project'
        creator = getattr(project.project, 'created_by_user', None) if getattr(project, 'project', None) else None
        project_manager = creator.get_full_name() or creator.username if creator else 'N/A'

        event_date = getattr(project, 'event_date', None)
        category_name = getattr(getattr(project, 'non_infra_category', None), 'type_name', '')
        address = getattr(project, 'address', None)
        barangay = getattr(address, 'barangay', '') if address else ''

        project_images = []
        if getattr(project, 'project', None):
            project_images = list(project.project.images.order_by('-created_at'))

        context['project_code'] = f'NINF-{compat_project.pk:05d}'
        context['project_type_label'] = 'Non-Infrastructure'
        context['project_manager'] = project_manager
        context['project_progress_value'] = None
        context['project_budget_value'] = None
        context['project_target_completion_date'] = event_date
        context['project_google_maps_url'] = ''
        context['project_images'] = project_images
        context['project_placeholder_image'] = static('images/project-placeholder.svg')
        context['project_gis'] = {
            'has_coordinates': False,
            'latitude': '',
            'longitude': '',
            'map_center_lat': 15.2915,
            'map_center_lng': 121.3386,
            'google_maps_url': '',
            'barangay': barangay,
            'municipality': 'Gabaldon',
            'province': 'Nueva Ecija',
            'status_label': 'Planned',
            'progress_label': 'Not available',
            'budget_label': 'N/A',
            'project_name': project_name,
            'project_code': context['project_code'],
            'project_type': 'Non-Infrastructure',
            'description': getattr(project, 'description', '') or '',
            'project_manager': project_manager,
            'contractor': '',
            'funding_source': '',
            'implementing_office': '',
            'start_date': event_date,
            'target_completion_date': event_date,
            'coordinate_message': 'Location has not yet been assigned.',
            'detail_url': reverse('mayor_projects:non_infrastructure_project_detail', args=[compat_project.pk]),
            'category_name': category_name,
            'proponent': getattr(project, 'proponent', '') or '',
            'beneficiaries': getattr(project, 'beneficiaries', None),
            'address': address,
        }
        return context


class NonInfrastructureProjectEditView(MayorsOfficeEditMixin, UpdateView):
    """Update an existing non-infrastructure project - Mayor's Office and admins only"""
    model = SystemNonInfrastructureProject
    form_class = NonInfrastructureProjectForm
    template_name = 'non_infrastructure/non_infrastructure_form.html'

    def get_success_url(self):
        return reverse('mayor_projects:non_infrastructure_project_list')

    def get_queryset(self):
        return SystemNonInfrastructureProject.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Edit'
        return context

    def form_valid(self, form):
        non = form.save(user=self.request.user, instance=self.get_object())
        self.object = SystemNonInfrastructureProject.objects.filter(non_infra_name=non.non_infra_name).first()
        return redirect(self.get_success_url())


class NonInfrastructureProjectDeleteView(MayorsOfficeEditMixin, DeleteView):
    """Delete a non-infrastructure project - Mayor's Office and admins only"""
    model = SystemNonInfrastructureProject
    template_name = 'non_infrastructure/non_infrastructure_confirm_delete.html'

    def get_success_url(self):
        return reverse('mayor_projects:non_infrastructure_project_list')

    def get_queryset(self):
        return SystemNonInfrastructureProject.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()

        context['cancel_url'] = reverse('mayor_projects:non_infrastructure_project_detail', args=[obj.pk])
        return context


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy, reverse, NoReverseMatch
from django.db import models
from django.db.models import Q, Sum
from django.templatetags.static import static
from .models import NonInfrastructureProject
from .forms import NonInfrastructureProjectForm

# Import UserProfile from system app
try:
    from apps.system.models import UserProfile
except ImportError:
    from system.models import UserProfile


class MayorsOfficeOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow only Mayor's Office users, explicitly exclude admins"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        # Explicitly exclude superusers/admins
        if self.request.user.is_superuser:
            return False
        try:
            return self.request.user.profile.department == 'mayor'
        except UserProfile.DoesNotExist:
            return False


class MayorsOfficeRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow only Mayor's Office users and admins"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        if self.request.user.is_superuser:
            return True
        try:
            return self.request.user.profile.department == 'mayor'
        except UserProfile.DoesNotExist:
            return False


class MayorsOfficeEditMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow Mayor's Office and admins to edit, prevent engineering office"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        # Allow admins
        if self.request.user.is_superuser:
            return True
        # Allow Mayor's office only, deny engineering office
        try:
            return self.request.user.profile.department == 'mayor'
        except UserProfile.DoesNotExist:
            return False

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

        # All Mayor's Office users see the same project pool.
        user_projects = NonInfrastructureProject.objects.all()

        context['total_projects'] = user_projects.count()

        # Count projects by progress
        context['planned_projects'] = user_projects.filter(overall_progress_percentage__isnull=True).count()
        context['in_progress_projects'] = user_projects.exclude(overall_progress_percentage__isnull=True).exclude(overall_progress_percentage=100).count()
        context['completed_projects'] = user_projects.filter(overall_progress_percentage=100).count()
        context['recent_projects'] = user_projects.order_by('-created_at')[:5]

        return context


class NonInfrastructureProjectListView(MayorsOfficeRequiredMixin, ListView):
    """Display list of non-infrastructure projects"""
    model = NonInfrastructureProject
    template_name = 'non_infrastructure/non_infrastructure_list.html'
    context_object_name = 'projects'
    paginate_by = 10

    def get_queryset(self):
        queryset = NonInfrastructureProject.objects.all()

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
        context['locations'] = NonInfrastructureProject.LOCATION_CHOICES
        context['categories'] = NonInfrastructureProject.PROJECT_CATEGORY_CHOICES
        return context


class NonInfrastructureProjectCreateView(MayorsOfficeOnlyMixin, CreateView):
    """Create a new non-infrastructure project - Mayor's Office only"""
    model = NonInfrastructureProject
    form_class = NonInfrastructureProjectForm
    template_name = 'non_infrastructure/non_infrastructure_form.html'

    def get_success_url(self):
        namespace = self.request.resolver_match.namespace
        if namespace:
            try:
                return reverse(f"{namespace}:non_infrastructure_project_list")
            except NoReverseMatch:
                pass
        try:
            return reverse('non_infrastructure_project_list')
        except NoReverseMatch:
            return reverse_lazy('non_infrastructure_project_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Create'
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class NonInfrastructureProjectDetailView(MayorsOfficeRequiredMixin, DetailView):
    """Display project details"""
    model = NonInfrastructureProject
    template_name = 'non_infrastructure/non_infrastructure_detail.html'
    context_object_name = 'project'

    def get_queryset(self):
        return NonInfrastructureProject.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        has_coordinates = project.latitude is not None and project.longitude is not None
        fallback_lat = 15.2915
        fallback_lng = 121.3386
        map_lat = float(project.latitude) if has_coordinates else fallback_lat
        map_lng = float(project.longitude) if has_coordinates else fallback_lng

        context['project_code'] = f'NINF-{project.pk:05d}'
        context['project_type_label'] = 'Non-Infrastructure'
        context['project_manager'] = project.created_by.get_full_name() or project.created_by.username
        context['project_progress_value'] = project.overall_progress_percentage
        context['project_budget_value'] = project.budget_cost
        context['project_target_completion_date'] = project.revised_completion_date or project.planned_end_date
        context['project_google_maps_url'] = f'https://www.google.com/maps?q={map_lat},{map_lng}'
        context['project_images'] = []
        context['project_placeholder_image'] = static('images/project-placeholder.svg')
        context['project_gis'] = {
            'has_coordinates': has_coordinates,
            'latitude': float(project.latitude) if has_coordinates else '',
            'longitude': float(project.longitude) if has_coordinates else '',
            'map_center_lat': map_lat,
            'map_center_lng': map_lng,
            'google_maps_url': f'https://www.google.com/maps?q={map_lat},{map_lng}',
            'barangay': project.get_location_display(),
            'municipality': 'Gabaldon',
            'province': 'Nueva Ecija',
            'status_label': 'Completed' if (project.overall_progress_percentage or 0) >= 100 else ('Ongoing' if (project.overall_progress_percentage or 0) > 0 else 'Planned'),
            'progress_label': f'{project.overall_progress_percentage:.2f}%' if project.overall_progress_percentage is not None else '0%',
            'budget_label': f'₱ {project.budget_cost:,.2f}' if project.budget_cost is not None else 'N/A',
            'project_name': project.title,
            'project_code': context['project_code'],
            'project_type': 'Non-Infrastructure',
            'description': project.description or '',
            'project_manager': context['project_manager'],
            'contractor': '',
            'funding_source': project.source_of_fund or '',
            'implementing_office': project.implementing_office or '',
            'start_date': project.planned_start_date,
            'target_completion_date': context['project_target_completion_date'],
            'coordinate_message': 'Location has not yet been assigned.' if not has_coordinates else '',
            'detail_url': reverse('non_infrastructure:non_infrastructure_project_detail', args=[project.pk]),
        }
        return context


class NonInfrastructureProjectEditView(MayorsOfficeEditMixin, UpdateView):
    """Update an existing non-infrastructure project - Mayor's Office and admins only"""
    model = NonInfrastructureProject
    form_class = NonInfrastructureProjectForm
    template_name = 'non_infrastructure/non_infrastructure_form.html'

    def get_success_url(self):
        namespace = self.request.resolver_match.namespace
        if namespace:
            try:
                return reverse(f"{namespace}:non_infrastructure_project_list")
            except NoReverseMatch:
                pass
        try:
            return reverse('non_infrastructure_project_list')
        except NoReverseMatch:
            return reverse_lazy('non_infrastructure_project_list')

    def get_queryset(self):
        return NonInfrastructureProject.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Edit'
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)


class NonInfrastructureProjectDeleteView(MayorsOfficeEditMixin, DeleteView):
    """Delete a non-infrastructure project - Mayor's Office and admins only"""
    model = NonInfrastructureProject
    template_name = 'non_infrastructure/non_infrastructure_confirm_delete.html'

    def get_success_url(self):
        namespace = self.request.resolver_match.namespace
        if namespace:
            try:
                return reverse(f"{namespace}:non_infrastructure_project_list")
            except NoReverseMatch:
                pass
        try:
            return reverse('non_infrastructure_project_list')
        except NoReverseMatch:
            return reverse_lazy('non_infrastructure_project_list')

    def get_queryset(self):
        return NonInfrastructureProject.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()

        # Attempt to resolve the properly namespaced detail URL based on current resolver namespace.
        namespace = self.request.resolver_match.namespace
        cancel_url = None
        if namespace:
            try:
                cancel_url = reverse(f"{namespace}:non_infrastructure_project_detail", args=[obj.pk])
            except NoReverseMatch:
                try:
                    cancel_url = reverse('non_infrastructure_project_detail', args=[obj.pk])
                except NoReverseMatch:
                    cancel_url = None
        else:
            try:
                cancel_url = reverse('non_infrastructure_project_detail', args=[obj.pk])
            except NoReverseMatch:
                cancel_url = None

        # Fallback: build a path by removing the trailing 'delete/' segment from the current path
        if not cancel_url:
            path = self.request.path
            if path.endswith('/delete/'):
                cancel_url = path[:-7]
            else:
                cancel_url = path.rstrip('/').rsplit('/', 1)[0] + '/'

        context['cancel_url'] = cancel_url
        return context


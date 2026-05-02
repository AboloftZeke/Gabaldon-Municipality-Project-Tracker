from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy, reverse, NoReverseMatch
from django.db import models
from django.db.models import Q, Sum
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

        # Admins see all projects; Mayor's Office see only their own
        if self.request.user.is_superuser:
            user_projects = NonInfrastructureProject.objects.all()
        else:
            user_projects = NonInfrastructureProject.objects.filter(created_by=self.request.user)

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
        if self.request.user.is_superuser:
            queryset = NonInfrastructureProject.objects.all()
        else:
            queryset = NonInfrastructureProject.objects.filter(created_by=self.request.user)

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
        if self.request.user.is_superuser:
            return NonInfrastructureProject.objects.all()
        return NonInfrastructureProject.objects.filter(created_by=self.request.user)


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
        if self.request.user.is_superuser:
            return NonInfrastructureProject.objects.all()
        return NonInfrastructureProject.objects.filter(created_by=self.request.user)

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
        if self.request.user.is_superuser:
            return NonInfrastructureProject.objects.all()
        return NonInfrastructureProject.objects.filter(created_by=self.request.user)

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


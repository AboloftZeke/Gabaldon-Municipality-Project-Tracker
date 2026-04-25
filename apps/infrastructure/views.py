from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy
from django.db import models
from django.db.models import Q, Sum
from .models import InfrastructureProject
from .forms import InfrastructureProjectForm

# Import UserProfile from system app
try:
    from apps.system.models import UserProfile
except ImportError:
    from system.models import UserProfile


class EngineeringOfficeRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow only engineering office users and admins"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        if self.request.user.is_superuser:
            return True
        try:
            return self.request.user.profile.department == 'engineer'
        except UserProfile.DoesNotExist:
            return False


class EngineerOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow only engineering office users, explicitly exclude admins"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        # Explicitly exclude superusers/admins
        if self.request.user.is_superuser:
            return False
        try:
            return self.request.user.profile.department == 'engineer'
        except UserProfile.DoesNotExist:
            return False


class ProjectDashboardView(EngineeringOfficeRequiredMixin, TemplateView):
    """Dashboard for engineering office to manage infrastructure projects"""
    template_name = 'projects/project_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Admins see all projects; engineers see only their own
        if self.request.user.is_superuser:
            user_projects = InfrastructureProject.objects.all()
        else:
            user_projects = InfrastructureProject.objects.filter(created_by=self.request.user)

        context['total_projects'] = user_projects.count()
        context['awarded_projects'] = user_projects.filter(award_status='awarded').count()
        context['ongoing_projects'] = user_projects.filter(award_status__in=['ongoing_bidding', 'awarded']).count()
        context['completed_projects'] = user_projects.filter(award_status='completed').count()
        context['recent_projects'] = user_projects.order_by('-created_at')[:5]

        total_abc = user_projects.filter(abc_amount__isnull=False).aggregate(
            total=models.Sum('abc_amount')
        )['total'] or 0
        context['total_investment'] = total_abc

        return context


class ProjectListView(EngineeringOfficeRequiredMixin, ListView):
    """Display list of infrastructure projects"""
    model = InfrastructureProject
    template_name = 'projects/project_list.html'
    context_object_name = 'projects'
    paginate_by = 10

    def get_queryset(self):
        if self.request.user.is_superuser:
            queryset = InfrastructureProject.objects.all()
        else:
            queryset = InfrastructureProject.objects.filter(created_by=self.request.user)

        # Filter by location
        location = self.request.GET.get('location', '').strip()
        if location:
            queryset = queryset.filter(location=location)

        # Filter by category
        category = self.request.GET.get('category', '').strip()
        if category:
            queryset = queryset.filter(category=category)

        # Filter by status
        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(award_status=status)

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['locations'] = InfrastructureProject.LOCATION_CHOICES
        context['categories'] = InfrastructureProject.PROJECT_CATEGORY_CHOICES
        context['statuses'] = InfrastructureProject.AWARD_STATUS_CHOICES
        return context


class ProjectCreateView(EngineerOnlyMixin, CreateView):
    """Create a new infrastructure project - engineers only"""
    model = InfrastructureProject
    form_class = InfrastructureProjectForm
    template_name = 'projects/project_form.html'
    success_url = reverse_lazy('project_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Create'
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ProjectDetailView(EngineeringOfficeRequiredMixin, DetailView):
    """Display project details"""
    model = InfrastructureProject
    template_name = 'projects/project_detail.html'
    context_object_name = 'project'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return InfrastructureProject.objects.all()
        return InfrastructureProject.objects.filter(created_by=self.request.user)


class ProjectEditView(EngineerOnlyMixin, UpdateView):
    """Update an existing infrastructure project - engineers only"""
    model = InfrastructureProject
    form_class = InfrastructureProjectForm
    template_name = 'projects/project_form.html'
    success_url = reverse_lazy('project_list')

    def get_queryset(self):
        if self.request.user.is_superuser:
            return InfrastructureProject.objects.all()
        return InfrastructureProject.objects.filter(created_by=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Edit'
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)


class ProjectDeleteView(EngineerOnlyMixin, DeleteView):
    """Delete an infrastructure project - engineers only"""
    model = InfrastructureProject
    template_name = 'projects/project_confirm_delete.html'
    success_url = reverse_lazy('project_list')

    def get_queryset(self):
        if self.request.user.is_superuser:
            return InfrastructureProject.objects.all()
        return InfrastructureProject.objects.filter(created_by=self.request.user)

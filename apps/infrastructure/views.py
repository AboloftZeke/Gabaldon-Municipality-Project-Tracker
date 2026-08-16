from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy, reverse, NoReverseMatch
from django.db import models
from django.db.models import Q, Sum
from django.templatetags.static import static
from .forms import InfrastructureProjectForm
from apps.system.models import InfrastructureProject as SystemInfrastructureProject
from apps.system.models import Infrastructure_Project, Project


def _department_for_user(user):
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'department', None) if profile is not None else None


class EngineeringOfficeRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow only engineering office users and admins"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        if self.request.user.is_superuser:
            return True
        department = _department_for_user(self.request.user)
        return department == 'engineer'


class EngineerOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow only engineering office users, explicitly exclude admins"""
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        # Explicitly exclude superusers/admins
        if self.request.user.is_superuser:
            return False
        department = _department_for_user(self.request.user)
        return department == 'engineer'

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


class ProjectDashboardView(EngineeringOfficeRequiredMixin, TemplateView):
    """Dashboard for engineering office to manage infrastructure projects"""
    template_name = 'projects/project_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # All engineering office users see the same project pool. Use normalized compatibility model.
        user_projects = SystemInfrastructureProject.objects.all()

        context['total_projects'] = user_projects.count()
        context['awarded_projects'] = user_projects.filter(award_status='awarded').count()
        context['ongoing_projects'] = user_projects.filter(award_status__in=['ongoing_bidding', 'awarded']).count()
        context['completed_projects'] = user_projects.filter(award_status='completed').count()
        # Build recent projects list and attach a `cover_image_url` attribute
        recent_qs = SystemInfrastructureProject.objects.order_by('-created_at')[:5]
        recent_projects = []
        for p in recent_qs:
            # Resolve normalized infra -> project -> first image (if any)
            infra_obj = Infrastructure_Project.objects.filter(infrastructure_id=p.id).select_related('project').first()
            cover = ''
            if infra_obj and getattr(infra_obj, 'project', None):
                # Use the latest uploaded image as the cover image
                first_img = infra_obj.project.images.order_by('-created_at').first()
                if first_img and getattr(first_img, 'image_url', None):
                    cover = first_img.image_url
            setattr(p, 'cover_image_url', cover)
            recent_projects.append(p)
        context['recent_projects'] = recent_projects

        # `SystemInfrastructureProject` is a compatibility (legacy) model that
        # does not expose `abc_amount` as a queryable DB field. Use the
        # normalized `Infrastructure_Project` model's related `Financial`
        # records to compute the total approved budget instead.
        infra_ids = list(user_projects.values_list('id', flat=True))
        total_abc = Infrastructure_Project.objects.filter(
            infrastructure_id__in=infra_ids,
            financial_records__approved_budget__isnull=False
        ).aggregate(total=Sum('financial_records__approved_budget'))['total'] or 0
        context['total_investment'] = total_abc

        return context


class ProjectListView(EngineeringOfficeRequiredMixin, ListView):
    """Display list of infrastructure projects"""
    model = SystemInfrastructureProject
    template_name = 'projects/project_list.html'
    context_object_name = 'projects'
    paginate_by = 10

    def get_queryset(self):
        queryset = SystemInfrastructureProject.objects.all()

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
        # Provide legacy choice constants from normalized/compatibility model if present
        context['locations'] = getattr(SystemInfrastructureProject, 'LOCATION_CHOICES', [])
        context['categories'] = getattr(SystemInfrastructureProject, 'PROJECT_CATEGORY_CHOICES', [])
        context['statuses'] = getattr(SystemInfrastructureProject, 'AWARD_STATUS_CHOICES', [])
        return context


class ProjectCreateView(EngineerOnlyMixin, CreateView):
    """Create a new infrastructure project - engineers only"""
    model = SystemInfrastructureProject
    form_class = InfrastructureProjectForm
    template_name = 'projects/project_form.html'

    def get_success_url(self):
        return reverse('engineering_projects:project_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Create'
        return context

    def form_valid(self, form):
        # Use the compatibility form save which writes to normalized tables
        infra = form.save(user=self.request.user)
        # Set the created object for the view to a compatibility instance
        # `SystemInfrastructureProject` is a compatibility model where the pk
        # column is `infrastructure_id`. Match by that id to reliably get the
        # compatibility instance for redirects and context.
        self.object = SystemInfrastructureProject.objects.filter(id=infra.infrastructure_id).first()
        return redirect(self.get_success_url())


class ProjectDetailView(EngineeringOfficeRequiredMixin, DetailView):
    """Display project details"""
    model = SystemInfrastructureProject
    template_name = 'projects/project_detail.html'
    context_object_name = 'project'

    def get_queryset(self):
        return SystemInfrastructureProject.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        has_coordinates = project.latitude is not None and project.longitude is not None
        fallback_lat = 15.2915
        fallback_lng = 121.3386
        map_lat = float(project.latitude) if has_coordinates else fallback_lat
        map_lng = float(project.longitude) if has_coordinates else fallback_lng

        context['project_code'] = f'INF-{project.pk:05d}'
        context['project_type_label'] = 'Infrastructure'
        context['project_manager'] = project.created_by.get_full_name() or project.created_by.username
        context['project_progress_value'] = project.physical_progress_percentage if project.physical_progress_percentage is not None else project.cost_progress_percentage
        context['project_budget_value'] = project.abc_amount if project.abc_amount is not None else project.contract_price
        context['project_target_completion_date'] = project.planned_end_date
        context['project_google_maps_url'] = f'https://www.google.com/maps?q={map_lat},{map_lng}'
        # Populate project images (latest first)
        imgs = []
        infra = Infrastructure_Project.objects.filter(infrastructure_id=project.id).select_related('project').first()
        if infra and getattr(infra, 'project', None):
            imgs = list(infra.project.images.order_by('-created_at'))
        context['project_images'] = imgs
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
            'status_label': project.get_award_status_display(),
            'progress_label': f'{context["project_progress_value"]:.2f}%' if context['project_progress_value'] is not None else '0%',
            'budget_label': f'₱ {context["project_budget_value"]:,.2f}' if context['project_budget_value'] is not None else 'N/A',
            'project_name': project.title,
            'project_code': context['project_code'],
            'project_type': 'Infrastructure',
            'description': project.description or '',
            'project_manager': context['project_manager'],
            'contractor': project.contractor or '',
            'funding_source': project.source_of_fund or '',
            'implementing_office': project.implementing_office or '',
            'start_date': project.planned_start_date,
            'target_completion_date': project.planned_end_date,
            'coordinate_message': 'Location has not yet been assigned.' if not has_coordinates else '',
            'detail_url': reverse('engineering_projects:project_detail', args=[project.pk]),
        }
        return context


class ProjectEditView(EngineerOnlyMixin, UpdateView):
    """Update an existing infrastructure project - engineers only"""
    model = SystemInfrastructureProject
    form_class = InfrastructureProjectForm
    template_name = 'projects/project_form.html'

    def get_success_url(self):
        return reverse('engineering_projects:project_list')

    def get_queryset(self):
        return SystemInfrastructureProject.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Edit'
        return context

    def form_valid(self, form):
        infra = form.save(user=self.request.user, instance=self.get_object())
        self.object = SystemInfrastructureProject.objects.filter(id=infra.infrastructure_id).first()
        return redirect(self.get_success_url())


class ProjectDeleteView(EngineerOnlyMixin, DeleteView):
    """Delete an infrastructure project - engineers only"""
    model = SystemInfrastructureProject
    template_name = 'projects/project_confirm_delete.html'

    def get_success_url(self):
        return reverse('engineering_projects:project_list')

    def get_queryset(self):
        return SystemInfrastructureProject.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()

        context['cancel_url'] = reverse('engineering_projects:project_detail', args=[obj.pk])
        return context


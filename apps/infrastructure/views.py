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
        context['user'] = self.request.user

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
                # Prefer the selected cover and fall back to the latest image.
                first_img = infra_obj.project.images.order_by(
                    '-is_cover',
                    '-created_at',
                ).first()
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

        # ---------------------------------------------------------
        # FIND THE NORMALIZED INFRASTRUCTURE PROJECT
        # ---------------------------------------------------------
        infra = (
            Infrastructure_Project.objects
            .filter(infrastructure_id=project.pk)
            .select_related(
                'project',
                'address',
                'category',
            )
            .prefetch_related('financial_records__fund_source')
            .first()
        )

        # ---------------------------------------------------------
        # BASIC PROJECT INFORMATION
        # ---------------------------------------------------------
        if infra and infra.project:
            base_project = infra.project
        else:
            base_project = project

        context['project_code'] = f'INF-{project.pk:05d}'
        context['project_type_label'] = 'Infrastructure'

        creator = getattr(base_project, 'created_by_user', None)

        if creator:
            context['project_manager'] = (
                creator.get_full_name() or creator.username
            )
        else:
            context['project_manager'] = 'N/A'

        # ---------------------------------------------------------
        # ADDRESS / GIS
        # ---------------------------------------------------------
        address = getattr(infra, 'address', None) if infra else None

        # -----------------------------------------
        # LOCATION
        # -----------------------------------------

        street = ''
        barangay = ''
        municipality = 'Gabaldon'
        province = 'Nueva Ecija'

        latitude = None
        longitude = None

        if address:
            street = address.street or ''
            barangay = address.barangay or ''
            municipality = address.municipality or 'Gabaldon'
            province = address.province or 'Nueva Ecija'

            latitude = address.latitude
            longitude = address.longitude


        # -----------------------------------------
        # GIS COORDINATES
        # -----------------------------------------

        has_coordinates = (
            latitude is not None and
            longitude is not None
        )

        fallback_lat = 15.2915
        fallback_lng = 121.3386

        if has_coordinates:
            map_lat = float(latitude)
            map_lng = float(longitude)
        else:
            map_lat = fallback_lat
            map_lng = fallback_lng

        # ---------------------------------------------------------
        # CATEGORY
        # ---------------------------------------------------------
        category_name = 'Not specified'

        if infra and infra.category:
            category_name = (
                infra.category.category_name or 'Not specified'
            )

        # ---------------------------------------------------------
        # IMPLEMENTING OFFICE
        # ---------------------------------------------------------
        implementing_office_name = 'Not specified'

        if infra and infra.implementing_office:
            implementing_office_name = (
                infra.implementing_office.office_name
                or 'Not specified'
            )

        # ---------------------------------------------------------
        # CONTRACTOR
        # ---------------------------------------------------------
        contractor_name = 'Not specified'

        if infra and infra.contractor:
            contractor_name = (
                infra.contractor.contractor_name
                or 'Not specified'
            )

        # ---------------------------------------------------------
        # FINANCIAL RECORD
        # ---------------------------------------------------------
        financial = None

        if infra:
            financial = (
                infra.financial_records
                .order_by('-financial_id')
                .first()
            )

        if financial:
            budget_value = financial.approved_budget
            contract_value = financial.bid_amount
            actual_expenditure = financial.actual_expenditure

            if financial.fund_source:
                funding_source_name = (
                    financial.fund_source.fund_source_name
                    or 'Not specified'
                )
            else:
                funding_source_name = 'Not specified'
        else:
            budget_value = None
            contract_value = None
            actual_expenditure = None
            funding_source_name = 'Not specified'

        # ---------------------------------------------------------
        # PROGRESS
        # ---------------------------------------------------------
        physical_progress = None
        cost_progress = None

        if infra:
            physical_progress = infra.physical_progress_percentage
            cost_progress = infra.cost_progress_percentage

        if physical_progress is not None:
            progress_value = physical_progress
        else:
            progress_value = cost_progress

        # ---------------------------------------------------------
        # DATES
        # ---------------------------------------------------------
        planned_start_date = None
        planned_end_date = None

        if infra:
            planned_start_date = infra.planned_start_date
            planned_end_date = infra.planned_end_date

        # ---------------------------------------------------------
        # CONTEXT VALUES
        # ---------------------------------------------------------
        context['project_progress_value'] = progress_value
        context['project_budget_value'] = budget_value
        context['project_target_completion_date'] = planned_end_date

        context['project_google_maps_url'] = (
            f'https://www.google.com/maps?q={map_lat},{map_lng}'
        )

        # ---------------------------------------------------------
        # PROJECT IMAGES
        # ---------------------------------------------------------
        imgs = []

        if infra and getattr(infra, 'project', None):
            imgs = list(
                infra.project.images.order_by('-is_cover', '-created_at')
            )

        context['project_images'] = imgs

        context['project_placeholder_image'] = static(
            'images/project-placeholder.svg'
        )

        # ---------------------------------------------------------
        # BARANGAY
        # ---------------------------------------------------------
        barangay = 'Not specified'

        if address and address.barangay:
            barangay = address.barangay

        # ---------------------------------------------------------
        # MUNICIPALITY
        # ---------------------------------------------------------
        municipality = 'Gabaldon'

        if address and address.municipality:
            municipality = address.municipality

        # ---------------------------------------------------------
        # PROVINCE
        # ---------------------------------------------------------
        province = 'Nueva Ecija'

        if address and address.province:
            province = address.province

        # ---------------------------------------------------------
        # STATUS
        # ---------------------------------------------------------
        status_label = 'Not specified'

        if hasattr(project, 'get_award_status_display'):
            status_label = (
                project.get_award_status_display()
                or 'Not specified'
            )

        # ---------------------------------------------------------
        # PROJECT NAME / DESCRIPTION
        # ---------------------------------------------------------
        project_name = getattr(
            base_project,
            'title',
            ''
        ) or 'Not specified'

        description = getattr(
            base_project,
            'description',
            ''
        ) or ''

        # ---------------------------------------------------------
        # GIS DATA
        # ---------------------------------------------------------
        context['project_gis'] = {
            'has_coordinates': has_coordinates,

            'latitude': (
                float(latitude)
                if has_coordinates
                else ''
            ),

            'longitude': (
                float(longitude)
                if has_coordinates
                else ''
            ),

            'map_center_lat': map_lat,
            'map_center_lng': map_lng,

            'google_maps_url': (
                f'https://www.google.com/maps'
                f'?q={map_lat},{map_lng}'
            ),
            'street': street,
            'barangay': barangay,
            'municipality': municipality,
            'province': province,

            'status_label': status_label,

            'progress_label': (
                f'{progress_value:.2f}%'
                if progress_value is not None
                else '0%'
            ),

            'budget_label': (
                f'₱ {budget_value:,.2f}'
                if budget_value is not None
                else 'N/A'
            ),

            'project_name': project_name,

            'project_code': context['project_code'],

            'project_type': 'Infrastructure',

            'description': description,

            'project_manager': context['project_manager'],

            'category': category_name,

            'contractor': contractor_name,

            'funding_source': funding_source_name,

            'implementing_office': implementing_office_name,

            'start_date': planned_start_date,

            'target_completion_date': planned_end_date,

            'coordinate_message': (
                'Location has not yet been assigned.'
                if not has_coordinates
                else ''
            ),

            'detail_url': reverse(
                'engineering_projects:project_detail',
                args=[project.pk]
            ),
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

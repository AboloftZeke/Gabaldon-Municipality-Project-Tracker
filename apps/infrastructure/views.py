from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse, NoReverseMatch
from django.db.models import Sum
from django.templatetags.static import static
from .forms import InfrastructureProjectForm
from apps.system.models import InfrastructureProject as SystemInfrastructureProject
from apps.system.models import (
    InfrastructureCategory,
    Infrastructure_Project,
)
from apps.system.publication_service import (
    publication_state,
    submit_project_for_review,
)


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
    """Dashboard for engineering office to manage infrastructure projects."""
    template_name = 'projects/project_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projects = (
            Infrastructure_Project.objects
            .select_related('address', 'category', 'project')
            .prefetch_related('project__images', 'financial_records')
        )

        context['total_projects'] = projects.count()
        context['awarded_projects'] = projects.filter(
            award_status='awarded'
        ).count()
        context['ongoing_projects'] = projects.filter(
            award_status='ongoing_bidding'
        ).count()
        context['completed_projects'] = projects.filter(
            award_status='completed'
        ).count()

        recent_projects = list(projects.order_by('-created_at')[:5])
        for project in recent_projects:
            cover = project.project.images.order_by(
                '-is_cover',
                '-created_at',
            ).first()
            project.cover_image_url = (
                cover.image_url if cover and cover.image_url else ''
            )
        context['recent_projects'] = recent_projects

        context['total_investment'] = (
            projects.filter(
                financial_records__approved_budget__isnull=False
            ).aggregate(
                total=Sum('financial_records__approved_budget')
            )['total']
            or 0
        )
        return context


class ProjectListView(EngineeringOfficeRequiredMixin, ListView):
    """Display normalized infrastructure projects."""
    model = Infrastructure_Project
    template_name = 'projects/project_list.html'
    context_object_name = 'projects'
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            Infrastructure_Project.objects
            .select_related('address', 'category', 'project')
            .prefetch_related('project__images', 'financial_records')
        )

        location = self.request.GET.get('location', '').strip()
        if location:
            queryset = queryset.filter(address__barangay=location)

        category = self.request.GET.get('category', '').strip()
        if category:
            queryset = queryset.filter(category_id=category)

        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(award_status=status)

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for project in context['projects']:
            cover = project.project.images.order_by(
                '-is_cover',
                '-created_at',
            ).first()
            project.cover_image_url = (
                cover.image_url if cover and cover.image_url else ''
            )
            project.publication_state = publication_state(project.project)
        context['locations'] = (
            Infrastructure_Project.objects
            .exclude(address__barangay__isnull=True)
            .exclude(address__barangay='')
            .values_list('address__barangay', flat=True)
            .distinct()
            .order_by('address__barangay')
        )
        context['categories'] = InfrastructureCategory.objects.filter(
            is_active=True
        ).order_by('category_name')
        context['statuses'] = Infrastructure_Project.AWARD_STATUS_CHOICES
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
        status_value = ''

        if hasattr(project, 'get_award_status_display'):
            status_label = (
                project.get_award_status_display()
                or 'Not specified'
            )

        if infra:
            status_value = infra.award_status or ''
        else:
            status_value = getattr(project, 'award_status', '') or ''

        status_class_map = {
            'ongoing_bidding': 'ongoing',
            'awarded': 'awarded',
            'completed': 'completed',
            'cancelled': 'cancelled',
        }
        context['project_status_class'] = status_class_map.get(
            status_value,
            'neutral',
        )

        # ---------------------------------------------------------
        # PROJECT NAME / DESCRIPTION
        # ---------------------------------------------------------
        project_name = (
            infra.infrastructure_title
            if infra else getattr(project, 'title', '')
        ) or 'Not specified'

        description = (
            infra.infrastructure_description
            if infra else getattr(project, 'description', '')
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

        schedule = (
            infra.schedules.order_by('-schedule_id').first()
            if infra else None
        )
        inspection = (
            infra.project.inspections.order_by(
                '-inspection_date',
                '-created_at',
            ).first()
            if infra and infra.project else None
        )

        context['project_details'] = {
            'pk': project.pk,
            'title': (
                infra.infrastructure_title
                if infra else getattr(project, 'title', '')
            ),
            'description': (
                infra.infrastructure_description
                if infra else getattr(project, 'description', '')
            ),
            'get_status_display': status_label,
            'get_award_status_display': status_label,
            'get_category_display': category_name,
            'implementing_office': implementing_office_name,
            'street': street,
            'get_barangay_display': barangay,
            'municipality': municipality,
            'province': province,
            'latitude': latitude,
            'longitude': longitude,
            'contractor': contractor_name,
            'get_procurement_method_display': (
                infra.get_procurement_method_display()
                if infra else ''
            ),
            'posting_date': getattr(schedule, 'posting_date', None),
            'pre_bid_date': getattr(schedule, 'pre_bid_date', None),
            'bidding_date': getattr(schedule, 'bidding_date', None),
            'notice_award_date': getattr(
                schedule,
                'notice_award_date',
                None,
            ),
            'notice_to_proceed_date': getattr(
                schedule,
                'notice_proceed_date',
                None,
            ),
            'abc_amount': budget_value,
            'contract_price': contract_value,
            'actual_expenditure': actual_expenditure,
            'source_of_fund': funding_source_name,
            'planned_start_date': planned_start_date,
            'planned_end_date': planned_end_date,
            'actual_start_date': getattr(
                schedule,
                'actual_start_date',
                None,
            ),
            'actual_completion_date': getattr(
                schedule,
                'actual_completion_date',
                None,
            ),
            'duration_days': getattr(schedule, 'duration_days', None),
            'cost_progress_percentage': cost_progress,
            'physical_progress_percentage': physical_progress,
            'inspection_date': getattr(
                inspection,
                'inspection_date',
                None,
            ),
            'inspection_completion_percentage': getattr(
                inspection,
                'completion_percentage',
                None,
            ),
            'inspection_findings': getattr(
                inspection,
                'findings',
                '',
            ),
            'inspection_remarks': getattr(
                inspection,
                'remarks',
                '',
            ),
            'created_by': creator,
            'created_at': getattr(infra, 'created_at', None),
            'updated_at': getattr(infra, 'updated_at', None),
        }

        if infra and infra.project:
            context['publication'] = publication_state(infra.project)
            context['publication_submit_url'] = reverse(
                'engineering_projects:project_submit_for_review',
                args=[project.pk],
            )
            context['can_manage_publication'] = not self.request.user.is_superuser

        return context


class ProjectSubmitForReviewView(EngineerOnlyMixin, View):
    """Submit an infrastructure working copy to the administrator."""

    def post(self, request, pk):
        infrastructure = get_object_or_404(
            Infrastructure_Project.objects.select_related('project'),
            pk=pk,
        )
        try:
            revision = submit_project_for_review(
                infrastructure.project,
                request.user,
            )
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            messages.success(
                request,
                f'Revision {revision.revision_number} was submitted for '
                'administrator review.',
            )
        return redirect(
            'engineering_projects:project_detail',
            pk=pk,
        )


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

    def form_valid(self, form):
        compat_project = self.get_object()
        normalized = (
            Infrastructure_Project.objects
            .filter(infrastructure_id=compat_project.pk)
            .select_related('project')
            .first()
        )
        success_url = self.get_success_url()

        if normalized is not None and normalized.project is not None:
            if normalized.project.publication_revisions.exists():
                messages.error(
                    self.request,
                    'A project with publication history cannot be deleted. '
                    'Contact an administrator to archive it instead.',
                )
                return redirect(
                    'engineering_projects:project_detail',
                    pk=compat_project.pk,
                )
            normalized.project.delete()
        else:
            compat_project.delete()

        return redirect(success_url)


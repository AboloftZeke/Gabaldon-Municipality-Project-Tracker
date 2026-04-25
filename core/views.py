from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Sum
from django.db import models
from django.conf import settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib import messages
from django.utils import timezone
from .forms import CustomUserCreationForm, CustomUserChangeForm, UserListFilterForm, InfrastructureProjectForm
from .models import InfrastructureProject


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Allow only staff users to access a view.
    """
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        return self.request.user.is_staff


class AdminRequiredMixin(StaffRequiredMixin):
    """
    Allow only admin users to access a view.
    """

    def test_func(self):
        return self.request.user.is_superuser


class LoginView(View):
    """
    Handle user login with Django's authentication system.
    """
    template_name = 'core/login.html'

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            if not user.is_staff:
                logout(request)
                return render(
                    request,
                    self.template_name,
                    {'error': 'Your account does not have access to this module.'}
                )
            return redirect('admin_dashboard')
        else:
            return render(request, self.template_name, {'error': 'Invalid credentials'})


class LogoutView(View):
    def get(self, request):
        logout(request)
        return render(request, 'core/logout.html')


class AdminDashboardView(StaffRequiredMixin, TemplateView):
    """
    Admin dashboard - placeholder view.
    """
    template_name = 'core/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_users'] = User.objects.count()
        context['total_admins'] = User.objects.filter(is_superuser=True).count()
        context['total_staff'] = User.objects.filter(is_staff=True, is_superuser=False).count()
        return context


class UserListView(AdminRequiredMixin, ListView):
    """
    Display list of users with optional department filtering.
    """
    model = User
    template_name = 'core/user_list.html'
    context_object_name = 'users'
    paginate_by = 10

    def get_queryset(self):
        queryset = User.objects.all().order_by('username')
        search = self.request.GET.get('search', '').strip()
        department = self.request.GET.get('department', '').strip()

        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        # Filter by department if provided
        if department:
            queryset = queryset.filter(profile__department=department)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = UserListFilterForm(self.request.GET)
        context['current_department'] = self.request.GET.get('department', '')
        return context


class UserCreateView(AdminRequiredMixin, CreateView):
    """
    Create a new user - placeholder view.
    """
    model = User
    form_class = CustomUserCreationForm
    template_name = 'core/user_form.html'
    success_url = reverse_lazy('user_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Create'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        # Log password creation
        from .models import PasswordChangeHistory
        PasswordChangeHistory.objects.create(
            user=self.object,
            changed_by=self.request.user,
            method='creation',
            notes=f'User created by {self.request.user.username}'
        )
        return response


class UserEditView(AdminRequiredMixin, UpdateView):
    """
    Edit an existing user - placeholder view.
    """
    model = User
    form_class = CustomUserChangeForm
    template_name = 'core/user_form.html'
    success_url = reverse_lazy('user_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Edit'
        return context


class UserDeleteView(AdminRequiredMixin, DeleteView):
    """
    Delete a user - placeholder view.
    """
    model = User
    template_name = 'core/user_confirm_delete.html'
    success_url = reverse_lazy('user_list')


class UserPasswordResetInitiateView(AdminRequiredMixin, DetailView):
    """
    Initiate password reset for a user by sending email with reset link.
    """
    model = User
    template_name = 'core/user_password_reset_confirm.html'
    context_object_name = 'reset_user'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Reset Password'
        return context

    def post(self, request, *args, **kwargs):
        user = self.get_object()

        # Generate token
        token_generator = PasswordResetTokenGenerator()
        token = token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        # Build password reset link (using Django's default password reset confirm view)
        reset_url = request.build_absolute_uri(
            reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        )

        # Prepare email context
        email_context = {
            'user': user,
            'reset_link': reset_url,
            'site_name': 'Municipality Project Tracker',
            'token_expiration_hours': 24,
        }

        # Send email
        try:
            # Text version
            text_message = render_to_string(
                'core/email/password_reset_email.txt',
                email_context,
                request=request
            )

            # HTML version
            html_message = render_to_string(
                'core/email/password_reset_email.html',
                email_context,
                request=request
            )

            send_mail(
                subject='Password Reset Request - Municipality Project Tracker',
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )

            # Log password reset in history
            from .models import PasswordChangeHistory
            PasswordChangeHistory.objects.create(
                user=user,
                changed_by=request.user,
                method='reset_link',
                notes=f'Password reset link sent by {request.user.username}'
            )

            # Show success message
            from django.contrib import messages
            messages.success(
                request,
                f'Password reset link has been sent to {user.email}'
            )
        except Exception as e:
            from django.contrib import messages
            messages.error(
                request,
                f'Error sending password reset email: {str(e)}'
            )

        return redirect('user_list')


class UserPasswordHistoryView(AdminRequiredMixin, DetailView):
    """
    Display password change history for a specific user.
    """
    model = User
    template_name = 'core/user_password_history.html'
    context_object_name = 'history_user'

    def get_context_data(self, **kwargs):
        from .models import PasswordChangeHistory
        context = super().get_context_data(**kwargs)
        user = self.get_object()
        context['password_changes'] = PasswordChangeHistory.objects.filter(
            user=user
        ).order_by('-changed_at')
        return context


class PasswordHistoryListView(AdminRequiredMixin, ListView):
    """
    Display all password changes across all users with filters.
    """
    template_name = 'core/password_history_list.html'
    context_object_name = 'password_changes'
    paginate_by = 20

    def get_queryset(self):
        from .models import PasswordChangeHistory
        queryset = PasswordChangeHistory.objects.select_related(
            'user', 'changed_by'
        ).order_by('-changed_at')

        # Filter by user
        user_filter = self.request.GET.get('user', '').strip()
        if user_filter:
            queryset = queryset.filter(user__username__icontains=user_filter)

        # Filter by method
        method_filter = self.request.GET.get('method', '').strip()
        if method_filter:
            queryset = queryset.filter(method=method_filter)

        # Filter by date range
        date_from = self.request.GET.get('date_from', '').strip()
        date_to = self.request.GET.get('date_to', '').strip()

        if date_from:
            from datetime import datetime
            try:
                start_date = datetime.strptime(date_from, '%Y-%m-%d')
                queryset = queryset.filter(changed_at__gte=start_date)
            except ValueError:
                pass

        if date_to:
            from datetime import datetime, timedelta
            try:
                end_date = datetime.strptime(date_to, '%Y-%m-%d')
                # Include entire day
                end_date = end_date + timedelta(days=1)
                queryset = queryset.filter(changed_at__lt=end_date)
            except ValueError:
                pass

        return queryset

    def get_context_data(self, **kwargs):
        from .models import PasswordChangeHistory
        context = super().get_context_data(**kwargs)

        # Add method choices for filter dropdown
        context['method_choices'] = PasswordChangeHistory.CHANGE_METHOD_CHOICES

        # Get all users for filter dropdown
        context['all_users'] = User.objects.all().order_by('username')

        # Add current filter values
        context['user_filter'] = self.request.GET.get('user', '')
        context['method_filter'] = self.request.GET.get('method', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')

        return context


class EngineeringOfficeRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Allow only engineering office users (or admins) to access a view.
    """
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        if self.request.user.is_superuser:
            return True
        # Check if user is in engineering office department
        if hasattr(self.request.user, 'profile'):
            return self.request.user.profile.department == 'engineer'
        return False


class EngineerOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Allow only engineering office users to access a view (excludes admins).
    """
    login_url = 'login'
    raise_exception = True

    def test_func(self):
        # Only allow engineers, explicitly exclude admins
        if self.request.user.is_superuser:
            return False
        # Check if user is in engineering office department
        if hasattr(self.request.user, 'profile'):
            return self.request.user.profile.department == 'engineer'
        return False


class ProjectDashboardView(EngineeringOfficeRequiredMixin, TemplateView):
    """
    Dashboard for engineering office to manage infrastructure projects.
    """
    template_name = 'core/project_dashboard.html'

    def get_context_data(self, **kwargs):
        from .models import InfrastructureProject
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
        
        # Get recent projects
        context['recent_projects'] = user_projects.order_by('-created_at')[:5]
        
        # Calculate total investment
        total_abc = user_projects.filter(abc_amount__isnull=False).aggregate(
            total=models.Sum('abc_amount')
        )['total'] or 0
        context['total_investment'] = total_abc
        
        return context


class ProjectListView(EngineeringOfficeRequiredMixin, ListView):
    """
    Display list of infrastructure projects.
    """
    model = InfrastructureProject
    template_name = 'core/project_list.html'
    context_object_name = 'projects'
    paginate_by = 10

    def get_queryset(self):
        from .models import InfrastructureProject
        
        # Admins see all projects; engineers see only their own
        if self.request.user.is_superuser:
            queryset = InfrastructureProject.objects.all()
        else:
            queryset = InfrastructureProject.objects.filter(
                created_by=self.request.user
            )
        
        queryset = queryset.order_by('-created_at')
        
        # Search filter
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(location__icontains=search)
                | Q(implementing_office__icontains=search)
            )
        
        # Category filter
        category = self.request.GET.get('category', '').strip()
        if category:
            queryset = queryset.filter(category=category)
        
        # Status filter
        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(award_status=status)
        
        # Location filter
        location = self.request.GET.get('location', '').strip()
        if location:
            queryset = queryset.filter(location=location)
        
        return queryset

    def get_context_data(self, **kwargs):
        from .models import InfrastructureProject
        context = super().get_context_data(**kwargs)
        context['category_choices'] = InfrastructureProject.PROJECT_CATEGORY_CHOICES
        context['status_choices'] = InfrastructureProject.AWARD_STATUS_CHOICES
        context['location_choices'] = InfrastructureProject.LOCATION_CHOICES
        context['current_search'] = self.request.GET.get('search', '')
        context['current_category'] = self.request.GET.get('category', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['current_location'] = self.request.GET.get('location', '')
        return context


class ProjectCreateView(EngineerOnlyMixin, CreateView):
    """
    Create a new infrastructure project.
    """
    model = InfrastructureProject
    template_name = 'core/project_form.html'
    form_class = InfrastructureProjectForm
    success_url = reverse_lazy('project_list')

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Create'
        return context


class ProjectDetailView(EngineeringOfficeRequiredMixin, DetailView):
    """
    Display detailed view of a project.
    """
    model = InfrastructureProject
    template_name = 'core/project_detail.html'
    context_object_name = 'project'

    def get_queryset(self):
        from .models import InfrastructureProject
        return InfrastructureProject.objects.filter(
            created_by=self.request.user
        )


class ProjectEditView(EngineeringOfficeRequiredMixin, UpdateView):
    """
    Edit an existing infrastructure project.
    """
    model = InfrastructureProject
    template_name = 'core/project_form.html'
    form_class = InfrastructureProjectForm
    success_url = reverse_lazy('project_list')

    def get_queryset(self):
        from .models import InfrastructureProject
        return InfrastructureProject.objects.filter(
            created_by=self.request.user
        )

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Edit'
        return context


class ProjectDeleteView(EngineeringOfficeRequiredMixin, DeleteView):
    """
    Delete an infrastructure project.
    """
    model = InfrastructureProject
    template_name = 'core/project_confirm_delete.html'
    success_url = reverse_lazy('project_list')

    def get_queryset(self):
        from .models import InfrastructureProject
        return InfrastructureProject.objects.filter(
            created_by=self.request.user
        )


class ProjectPublishView(EngineerOnlyMixin, DetailView):
    """
    Submit a project for admin review/publication.
    """
    model = InfrastructureProject
    template_name = 'core/project_publish_confirm.html'
    context_object_name = 'project'

    def get_queryset(self):
        return InfrastructureProject.objects.filter(
            created_by=self.request.user,
            publication_status='draft'
        )

    def post(self, request, *args, **kwargs):
        project = self.get_object()
        project.publication_status = 'pending_review'
        project.save()
        
        messages.success(request, f"Project '{project.title}' submitted for review.")
        return redirect('project_detail', pk=project.pk)


class ProjectReviewListView(AdminRequiredMixin, ListView):
    """
    List projects pending admin review.
    """
    model = InfrastructureProject
    template_name = 'core/project_review_list.html'
    context_object_name = 'projects'
    paginate_by = 10

    def get_queryset(self):
        return InfrastructureProject.objects.filter(
            publication_status='pending_review'
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pending_count'] = self.get_queryset().count()
        return context


class ProjectReviewView(AdminRequiredMixin, DetailView):
    """
    Review and approve/reject projects submitted by engineering office.
    """
    model = InfrastructureProject
    template_name = 'core/project_review.html'
    context_object_name = 'project'

    def get_queryset(self):
        return InfrastructureProject.objects.filter(
            publication_status__in=['pending_review', 'needs_revision']
        )

    def post(self, request, *args, **kwargs):
        project = self.get_object()
        action = request.POST.get('action')
        comments = request.POST.get('comments', '').strip()

        if action == 'approve':
            project.publication_status = 'published'
            project.review_comments = ''
            msg = f"Project '{project.title}' has been approved and published."
        elif action == 'revision':
            if not comments:
                messages.error(request, "Please provide comments for revision.")
                return redirect('project_review', pk=project.pk)
            project.publication_status = 'needs_revision'
            project.review_comments = comments
            msg = f"Project '{project.title}' marked for revision with comments."
        elif action == 'reject':
            if not comments:
                messages.error(request, "Please provide reason for rejection.")
                return redirect('project_review', pk=project.pk)
            project.publication_status = 'rejected'
            project.review_comments = comments
            msg = f"Project '{project.title}' has been rejected."
        else:
            messages.error(request, "Invalid action.")
            return redirect('project_review', pk=project.pk)

        project.reviewed_by = request.user
        project.reviewed_at = timezone.now()
        project.save()

        messages.success(request, msg)
        return redirect('project_review_list')

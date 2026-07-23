from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse_lazy, reverse
from django.db.models import Q
from django.conf import settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from .forms import CustomUserCreationForm, CustomUserChangeForm, UserListFilterForm
import json


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
    Redirects to role-specific dashboard.
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
            # Redirect based on user role
            if user.is_superuser:
                return redirect('admin_dashboard')
            try:
                if user.profile.department == 'engineer':
                    return redirect('engineering_dashboard')
                elif user.profile.department == 'mayor':
                    return redirect('mayor_dashboard')
            except:
                pass
            return redirect('admin_dashboard')
        else:
            return render(request, self.template_name, {'error': 'Invalid credentials'})


class LogoutView(View):
    def get(self, request):
        logout(request)
        return render(request, 'core/logout.html')


class PublicDashboardView(TemplateView):
    """
    Public transparency dashboard showing live project data.
    """
    template_name = 'Dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from apps.infrastructure.models import InfrastructureProject
        from apps.non_infrastructure.models import NonInfrastructureProject

        infra_qs = InfrastructureProject.objects.all().order_by('-created_at')
        noninfra_qs = NonInfrastructureProject.objects.all().order_by('-created_at')

        infra_total = infra_qs.count()
        noninfra_total = noninfra_qs.count()
        total_projects = infra_total + noninfra_total

        infra_completed = infra_qs.filter(award_status='completed').count()
        infra_ongoing = infra_qs.filter(award_status__in=['ongoing_bidding', 'awarded']).count()

        noninfra_completed = noninfra_qs.filter(overall_progress_percentage__gte=100).count()
        noninfra_ongoing = noninfra_qs.filter(
            overall_progress_percentage__gt=0,
            overall_progress_percentage__lt=100,
        ).count()
        noninfra_planned = noninfra_qs.filter(
            Q(overall_progress_percentage__isnull=True) | Q(overall_progress_percentage=0)
        ).count()

        completed_projects = infra_completed + noninfra_completed
        ongoing_projects = infra_ongoing + noninfra_ongoing

        infra_budget_total = sum((p.abc_amount or p.contract_price or 0) for p in infra_qs)
        noninfra_budget_total = sum((p.budget_cost or 0) for p in noninfra_qs)
        total_budget = infra_budget_total + noninfra_budget_total

        if total_projects:
            portfolio_progress = round((completed_projects / total_projects) * 100)
        else:
            portfolio_progress = 0

        rows = []

        infra_location_map = dict(InfrastructureProject.LOCATION_CHOICES)
        noninfra_location_map = dict(NonInfrastructureProject.LOCATION_CHOICES)
        location_options_map = {**infra_location_map, **noninfra_location_map}

        category_options = []
        for value, label in InfrastructureProject.PROJECT_CATEGORY_CHOICES:
            category_options.append((f'infra:{value}', f'Infrastructure - {label}'))
        for value, label in NonInfrastructureProject.PROJECT_CATEGORY_CHOICES:
            category_options.append((f'noninfra:{value}', f'Non-Infrastructure - {label}'))

        for p in infra_qs:
            if p.award_status == 'completed':
                status_key = 'completed'
                status_label = 'Completed'
            elif p.award_status in ['ongoing_bidding', 'awarded']:
                status_key = 'ongoing'
                status_label = 'Ongoing'
            else:
                status_key = 'planned'
                status_label = 'Planned'

            detail_url = '#'
            try:
                detail_url = reverse('infrastructure_default:project_detail', args=[p.pk])
            except Exception:
                pass

            rows.append({
                'record_id': f'infra-{p.pk}',
                'category': 'infra',
                'project_category_key': f'infra:{p.category}',
                'project_category_label': f'Infrastructure - {p.get_category_display()}',
                'type_label': 'Infrastructure',
                'title': p.title,
                'location_key': p.location,
                'location': p.get_location_display(),
                'status_key': status_key,
                'status_label': status_label,
                'budget': p.abc_amount or p.contract_price or 0,
                'progress': p.physical_progress_percentage or 0,
                'office': p.contractor or p.implementing_office,
                'created_at': p.created_at,
                'detail_url': detail_url,
            })

        for p in noninfra_qs:
            progress_value = p.overall_progress_percentage or 0
            if progress_value >= 100:
                status_key = 'completed'
                status_label = 'Completed'
            elif progress_value > 0:
                status_key = 'ongoing'
                status_label = 'Ongoing'
            else:
                status_key = 'planned'
                status_label = 'Planned'

            detail_url = '#'
            try:
                detail_url = reverse('non_infrastructure_default:non_infrastructure_project_detail', args=[p.pk])
            except Exception:
                pass

            rows.append({
                'record_id': f'noninfra-{p.pk}',
                'category': 'noninfra',
                'project_category_key': f'noninfra:{p.category}',
                'project_category_label': f'Non-Infrastructure - {p.get_category_display()}',
                'type_label': 'Non-Infrastructure',
                'title': p.title,
                'location_key': p.location,
                'location': p.get_location_display(),
                'status_key': status_key,
                'status_label': status_label,
                'budget': p.budget_cost or 0,
                'progress': progress_value,
                'office': p.implementing_office,
                'created_at': p.created_at,
                'detail_url': detail_url,
            })

        rows.sort(key=lambda x: x['created_at'], reverse=True)

        context.update({
            'total_projects': total_projects,
            'infra_total': infra_total,
            'noninfra_total': noninfra_total,
            'completed_projects': completed_projects,
            'ongoing_projects': ongoing_projects,
            'planned_projects': noninfra_planned,
            'portfolio_progress': portfolio_progress,
            'total_budget': total_budget,
            'project_rows': rows,
            'recent_rows': rows[:8],
            'project_categories': category_options,
            'location_options': sorted(location_options_map.items(), key=lambda x: x[1]),
        })

        return context


class AdminDashboardView(StaffRequiredMixin, TemplateView):
    """
    Admin dashboard for system administrators only.
    """
    template_name = 'core/admin_dashboard.html'

    def test_func(self):
        return self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_users'] = User.objects.count()
        context['total_admins'] = User.objects.filter(is_superuser=True).count()
        context['total_staff'] = User.objects.filter(is_staff=True, is_superuser=False).count()
        return context


class EngineeringDashboardView(StaffRequiredMixin, TemplateView):
    """
    Engineering Office dashboard.
    """
    template_name = 'core/engineering_dashboard.html'

    def test_func(self):
        try:
            return self.request.user.profile.department == 'engineer'
        except:
            return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.infrastructure.models import InfrastructureProject
        
        user_projects = InfrastructureProject.objects.all()
        context['total_projects'] = user_projects.count()
        context['awarded_projects'] = user_projects.filter(award_status='awarded').count()
        context['ongoing_projects'] = user_projects.filter(award_status__in=['ongoing_bidding', 'awarded']).count()
        context['completed_projects'] = user_projects.filter(award_status='completed').count()
        
        return context


class MayorDashboardView(StaffRequiredMixin, TemplateView):
    """
    Mayor's Office dashboard.
    """
    template_name = 'core/mayor_dashboard.html'

    def test_func(self):
        try:
            return self.request.user.profile.department == 'mayor'
        except:
            return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.non_infrastructure.models import NonInfrastructureProject
        
        user_projects = NonInfrastructureProject.objects.all()
        context['total_projects'] = user_projects.count()
        context['planned_projects'] = user_projects.filter(overall_progress_percentage__isnull=True).count()
        context['in_progress_projects'] = user_projects.exclude(overall_progress_percentage__isnull=True).exclude(overall_progress_percentage=100).count()
        context['completed_projects'] = user_projects.filter(overall_progress_percentage=100).count()
        
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
    Create a new user - shows form, then redirects to confirmation.
    """
    model = User
    form_class = CustomUserCreationForm
    template_name = 'core/user_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Create'
        return context

    def get_initial(self):
        initial = super().get_initial()
        form_data = self.request.session.get('user_create_form_data')
        if form_data:
            initial.update(form_data)
        return initial

    def form_valid(self, form):
        self.request.session['user_create_form_data'] = {
            'username': form.cleaned_data['username'],
            'email': form.cleaned_data['email'],
            'first_name': form.cleaned_data['first_name'],
            'last_name': form.cleaned_data['last_name'],
            'role': form.cleaned_data['role'],
            'password1': form.cleaned_data['password1'],
        }
        return redirect('user_create_confirm')


class UserEditView(AdminRequiredMixin, UpdateView):
    """
    Edit an existing user - shows form, then redirects to confirmation.
    """
    model = User
    form_class = CustomUserChangeForm
    template_name = 'core/user_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Edit'
        return context

    def get_initial(self):
        initial = super().get_initial()
        user = self.get_object()
        form_data = self.request.session.get(f'user_edit_form_data_{user.pk}')
        if form_data:
            initial.update(form_data['new_data'])
        return initial

    def form_valid(self, form):
        user = self.get_object()
        old_data = {
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_active': user.is_active,
        }
        if hasattr(user, 'profile'):
            old_role_map = {'admin': 'admin', 'engineer': 'engineering', 'mayor': 'mayors'}
            old_data['role'] = old_role_map.get(user.profile.department, 'engineering')

        new_data = {
            'username': form.cleaned_data['username'],
            'email': form.cleaned_data['email'],
            'first_name': form.cleaned_data['first_name'],
            'last_name': form.cleaned_data['last_name'],
            'is_active': form.cleaned_data['is_active'],
            'role': form.cleaned_data['role'],
        }

        self.request.session[f'user_edit_form_data_{user.pk}'] = {
            'old_data': old_data,
            'new_data': new_data,
        }
        return redirect('user_edit_confirm', pk=user.pk)


class UserCreateConfirmView(AdminRequiredMixin, TemplateView):
    """
    Confirmation page for user creation - displays summary and saves on final confirmation.
    """
    template_name = 'core/user_create_confirm.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form_data = self.request.session.get('user_create_form_data')

        if not form_data:
            context['error'] = 'Session expired. Please try again.'
            return context

        context['form_data'] = form_data
        return context

    def post(self, request, *args, **kwargs):
        form_data = request.session.get('user_create_form_data')

        if not form_data:
            messages.error(request, 'Session expired. Please try again.')
            return redirect('user_create')

        try:
            # The confirmation step reuses the original form data, so mirror the
            # password into password2 to satisfy the form's validation on submit.
            confirm_data = form_data.copy()
            confirm_data.setdefault('password2', confirm_data.get('password1', ''))
            form = CustomUserCreationForm(confirm_data)
            if form.is_valid():
                user = form.save(commit=True)

                from .models import PasswordChangeHistory
                PasswordChangeHistory.objects.create(
                    user=user,
                    changed_by=request.user,
                    method='creation',
                    notes=f'User created by {request.user.username}'
                )

                del request.session['user_create_form_data']
                messages.success(request, f"User '{user.username}' created successfully.")
                return redirect('user_list')
            else:
                request.session['user_create_form_data'] = form_data
                messages.error(request, 'Validation failed. Please check your input.')
                return redirect('user_create')
        except Exception as e:
            messages.error(request, f'Error creating user: {str(e)}')
            return redirect('user_create')


class UserEditConfirmView(AdminRequiredMixin, TemplateView):
    """
    Confirmation page for user editing - displays old/new comparison and saves on final confirmation.
    """
    template_name = 'core/user_edit_confirm.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pk = kwargs.get('pk')
        form_data = self.request.session.get(f'user_edit_form_data_{pk}')

        if not form_data:
            context['error'] = 'Session expired. Please try again.'
            return context

        context['form_data'] = form_data
        context['user_pk'] = pk

        user = User.objects.get(pk=pk)
        context['user'] = user

        return context

    def post(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        form_data = request.session.get(f'user_edit_form_data_{pk}')

        if not form_data:
            messages.error(request, 'Session expired. Please try again.')
            return redirect('user_edit', pk=pk)

        try:
            user = User.objects.get(pk=pk)

            new_data = form_data['new_data']
            form = CustomUserChangeForm(new_data, instance=user)

            if form.is_valid():
                form.save(commit=True)
                del request.session[f'user_edit_form_data_{pk}']
                messages.success(request, f"User '{user.username}' updated successfully.")
                return redirect('user_list')
            else:
                messages.error(request, 'Validation failed. Please check your input.')
                return redirect('user_edit', pk=pk)
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
            return redirect('user_list')
        except Exception as e:
            messages.error(request, f'Error updating user: {str(e)}')
            return redirect('user_edit', pk=pk)


class UserDeactivateView(AdminRequiredMixin, View):
    """
    Deactivate a user.
    """
    template_name = 'core/user_confirm_deactivate.html'

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        can_deactivate = True
        warning_message = None

        if user == request.user:
            can_deactivate = False
            warning_message = 'You cannot deactivate your own account.'
        elif (
            user.is_superuser
            and user.is_active
            and User.objects.filter(is_superuser=True, is_active=True).count() == 1
        ):
            can_deactivate = False
            warning_message = 'Cannot deactivate the last active administrator.'

        return render(request, self.template_name, {
            'object': user,
            'can_deactivate': can_deactivate,
            'warning_message': warning_message,
        })

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        # Prevent deactivating yourself
        if user == request.user:
            messages.error(request, "You cannot deactivate your own account.")
            return redirect('user_list')

        # Prevent deactivating the last active admin
        if (
            user.is_superuser
            and user.is_active
            and User.objects.filter(is_superuser=True, is_active=True).count() == 1
        ):
            messages.error(request, "Cannot deactivate the last active administrator.")
            return redirect('user_list')

        user.is_active = False
        user.save()

        messages.success(request, f"User '{user.username}' has been deactivated.")
        return redirect('user_list')
    
class UserActivateView(AdminRequiredMixin, View):
    """
    Activate a user - placeholder view.
    """
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        user.is_active = True
        user.save()

        messages.success(request, f"User '{user.username}' has been activated.")
        return redirect('user_list')


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

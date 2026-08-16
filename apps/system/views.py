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
from django.utils.crypto import get_random_string
from .forms import (
    CustomUserCreationForm,
    CustomUserChangeForm,
    UserListFilterForm,
    UserPasswordChangeForm,
)
import json


def _department_for_user(user):
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'department', None) if profile is not None else None


def _password_history_model():
    return User._meta.get_field('password_changes').related_model


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
    Redirects to password change if a temporary password must be replaced.
    Otherwise redirects to the user's role-specific dashboard.
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

            department = _department_for_user(user)

            if getattr(getattr(user, 'flags', None), 'must_change_password', False):
                return redirect('password_change')

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
            if department == 'engineer':
                return redirect('engineering_dashboard')
            elif department == 'mayor':
                return redirect('mayor_dashboard')
            return redirect('admin_dashboard')
        else:
            return render(request, self.template_name, {'error': 'Invalid credentials'})


class LogoutView(View):
    def get(self, request):
        logout(request)
        return render(request, 'core/logout.html')


class PublicDashboardView(TemplateView):
    template_name = 'Dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from django.utils import timezone
        from apps.system.models import InfrastructureProject, Non_Infrastructure_Project
        # Static choice lists still only live on the legacy model classes.
        # We use them here purely as UI lookup data (barangay/category labels),
        # not for storage or querying — the normalized models are source of truth for data.
        from apps.infrastructure.models import InfrastructureProject as LegacyInfrastructureProject
        from apps.non_infrastructure.models import NonInfrastructureProject as LegacyNonInfrastructureProject
        from apps.system.models import InfrastructureCategory, NonInfrastructureCategory

        infra_qs = InfrastructureProject.objects.all().order_by('-created_at')
        noninfra_qs = Non_Infrastructure_Project.objects.select_related(
            'project', 'project__created_by_user', 'address', 'non_infra_category'
        ).order_by('-created_at')

        infra_total = infra_qs.count()
        noninfra_total = noninfra_qs.count()
        total_projects = infra_total + noninfra_total

        infra_completed = infra_qs.filter(award_status='completed').count()
        infra_ongoing = infra_qs.filter(award_status__in=['ongoing_bidding', 'awarded']).count()

        # Non-infra has no progress/status field in the normalized schema yet.
        # Deriving a rough status from event_date so rows aren't all "Planned" forever;
        # revisit if/when a real status field is added (see MIGRATION_PLAN item 6).
        today = timezone.now().date()
        noninfra_completed = noninfra_qs.filter(event_date__lt=today).count()
        noninfra_ongoing = noninfra_qs.filter(event_date=today).count()
        noninfra_planned = noninfra_total - noninfra_completed - noninfra_ongoing

        completed_projects = infra_completed + noninfra_completed
        ongoing_projects = infra_ongoing + noninfra_ongoing

        infra_budget_total = sum((p.abc_amount or p.contract_price or 0) for p in infra_qs)
        # No Financial record exists for non-infra projects in the normalized schema
        # (Financial only FKs to Infrastructure_Project right now). Contributes 0
        # until that's resolved — see MIGRATION_PLAN item 6.
        noninfra_budget_total = 0
        total_budget = infra_budget_total + noninfra_budget_total

        if total_projects:
            portfolio_progress = round((completed_projects / total_projects) * 100)
        else:
            portfolio_progress = 0

        rows = []

        infra_location_map = dict(LegacyInfrastructureProject.LOCATION_CHOICES)
        noninfra_location_map = dict(LegacyNonInfrastructureProject.LOCATION_CHOICES)
        location_options_map = {**infra_location_map, **noninfra_location_map}

        category_options = []
        for value, label in LegacyInfrastructureProject.PROJECT_CATEGORY_CHOICES:
            category_options.append((f'infra:{value}', f'Infrastructure - {label}'))
        for cat in NonInfrastructureCategory.objects.all().order_by('type_name'):
            category_options.append((f'noninfra:{cat.type_code}', f'Non-Infrastructure - {cat.type_name}'))

        for p in noninfra_qs:
            status_key = 'planned'
            status_label = 'Planned'

            category_code = (
                p.non_infra_category.type_code
                if p.non_infra_category else ''
            )
            category_name = (
                p.non_infra_category.type_name
                if p.non_infra_category else ''
            )

            location = str(p.address) if p.address else ''

            creator = p.project.created_by_user if p.project else None

            detail_url = '#'
            try:
                detail_url = reverse(
                    'mayor_projects:non_infrastructure_project_detail',
                    args=[p.pk]
                )
            except Exception:
                pass

            rows.append({
                'record_id': f'noninfra-{p.pk}',
                'category': 'noninfra',
                'project_category_key': f'noninfra:{category_code}',
                'project_category_label': (
                    f'Non-Infrastructure - {category_name}'
                    if category_name
                    else 'Non-Infrastructure'
                ),
                'type_label': 'Non-Infrastructure',

                'title': p.non_infra_name,

                'location_key': p.address_id,
                'location': location,

                'status_key': status_key,
                'status_label': status_label,

                'office': '',
                'implementing_office': '',
                'category_label': category_name,

                'contractor': '',
                'procurement_method': '',
                'source_of_fund': '',

                'budget': 0,
                'budget_amount': 0,
                'abc_amount': '',
                'contract_price': '',

                'progress': 0,
                'progress_percentage': 0,
                'overall_progress_percentage': '',
                'cost_progress_percentage': '',
                'physical_progress_percentage': '',

                'description': p.description,

                'venue_name': p.venue_name or '',
                'event_date': p.event_date,
                'start_time': (
                    p.start_time.strftime('%H:%M')
                    if p.start_time else ''
                ),
                'end_time': (
                    p.end_time.strftime('%H:%M')
                    if p.end_time else ''
                ),

                'planned_start_date': p.event_date,
                'planned_end_date': None,
                'actual_start_date': None,

                'created_by_name': (
                    creator.get_full_name() or creator.username
                    if creator else ''
                ),

                'created_at': p.created_at,
                'updated_at': p.updated_at,
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
        department = _department_for_user(self.request.user)
        return department == 'engineer'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.system.models import InfrastructureProject
        
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
        department = _department_for_user(self.request.user)
        return department == 'mayor'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.system.models import NonInfrastructureProject
        
        user_projects = NonInfrastructureProject.objects.all()

        context['total_projects'] = user_projects.count()

        # Non-infrastructure projects no longer have a progress/status field
        # in the redesigned schema, so these cannot be calculated reliably.
        context['planned_projects'] = 0
        context['in_progress_projects'] = 0
        context['completed_projects'] = 0
        
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
            form = CustomUserCreationForm(form_data)

            if form.is_valid():
                temporary_password = get_random_string(
                    length=12,
                    allowed_chars='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()'
                    )
                user = form.save(
                    commit=True,
                    temporary_password=temporary_password
                )

                # Persist a runtime flag so the application enforces password
                # change on first login without recreating the archived profile.
                from .models import UserFlag
                UserFlag.objects.update_or_create(user=user, defaults={'must_change_password': True})

                del request.session['user_create_form_data']
                messages.success(
                    request,
                     f"User '{user.username}' created successfully. "
                     f" Temporary password: {temporary_password}. User will be required to change password on first login.")
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

        # Prevent deactivating the last active administrator
        remaining_admins = User.objects.filter(
            is_superuser=True,
            is_active=True
        ).exclude(pk=user.pk).count()

        if user.is_superuser and remaining_admins == 0:
            messages.error(
                request,
                "At least one active administrator must remain in the system."
            )
            return redirect('user_list')

        # Prevent deactivating yourself
        if user == request.user:
            messages.error(request, "You cannot deactivate your own account.")
            return redirect('user_list')

        user.is_active = False
        user.save()

        messages.success(
            request,
            f"User '{user.username}' has been deactivated."
        )
        return redirect('user_list')
    
class UserActivateView(AdminRequiredMixin, View):
    """
    Activate a user.
    """
    template_name = 'core/user_confirm_activate.html'

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        return render(request, self.template_name, {
            'object': user,
        })

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        user.is_active = True
        user.save()

        messages.success(
            request,
            f"User '{user.username}' has been activated."
        )
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
            history_model = _password_history_model()
            history_model.objects.create(
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
        context = super().get_context_data(**kwargs)
        user = self.get_object()
        history_model = _password_history_model()
        context['password_changes'] = history_model.objects.filter(
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
        history_model = _password_history_model()
        queryset = history_model.objects.select_related(
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
        context = super().get_context_data(**kwargs)
        history_model = _password_history_model()

        # Add method choices for filter dropdown
        context['method_choices'] = history_model.CHANGE_METHOD_CHOICES

        # Get all users for filter dropdown
        context['all_users'] = User.objects.all().order_by('username')

        # Add current filter values
        context['user_filter'] = self.request.GET.get('user', '')
        context['method_filter'] = self.request.GET.get('method', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')

        return context

class PasswordChangeView(LoginRequiredMixin, View):
    """
    Allow the logged-in user to change their password.
    Used for both mandatory temporary-password changes and normal
    password changes.
    """
    template_name = 'core/password_change.html'

    def get(self, request):
        form = UserPasswordChangeForm(request.user)

        return render(
            request,
            self.template_name,
            {'form': form}
        )

    def post(self, request):
        form = UserPasswordChangeForm(
            request.user,
            request.POST
        )

        if form.is_valid():
            form.save()

            # Clear the temporary-password requirement.
            from .models import UserFlag
            UserFlag.objects.update_or_create(
                user=request.user,
                defaults={'must_change_password': False},
            )

            messages.success(
                request,
                'Your password has been changed successfully.'
            )

            # Re-authenticate the session because set_password()
            # changes the user's password hash.
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, request.user)

            # Return the user to their normal dashboard.
            if request.user.is_superuser:
                return redirect('admin_dashboard')

            department = _department_for_user(request.user)
            if department == 'engineer':
                return redirect('engineering_dashboard')
            elif department == 'mayor':
                return redirect('mayor_dashboard')

            return redirect('admin_dashboard')

        return render(
            request,
            self.template_name,
            {'form': form}
        )
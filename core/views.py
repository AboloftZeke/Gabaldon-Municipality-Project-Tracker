from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse_lazy, reverse
from django.db.models import Q
from django.conf import settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from .forms import CustomUserCreationForm, CustomUserChangeForm, UserListFilterForm


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
    """
    Handle user logout.
    """
    def get(self, request):
        logout(request)
        return redirect('login')


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
    Display list of users - placeholder view.
    """
    model = User
    template_name = 'core/user_list.html'
    context_object_name = 'users'
    paginate_by = 10

    def get_queryset(self):
        queryset = User.objects.all().order_by('username')
        search = self.request.GET.get('search', '').strip()

        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = UserListFilterForm(self.request.GET)
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

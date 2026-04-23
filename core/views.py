from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.db.models import Q
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

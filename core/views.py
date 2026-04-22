from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from .forms import CustomUserCreationForm, CustomUserChangeForm, UserListFilterForm


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


class AdminDashboardView(LoginRequiredMixin, TemplateView):
    """
    Admin dashboard - placeholder view.
    """
    template_name = 'core/admin_dashboard.html'
    login_url = 'login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_users'] = User.objects.count()
        return context


class UserListView(LoginRequiredMixin, ListView):
    """
    Display list of users - placeholder view.
    """
    model = User
    template_name = 'core/user_list.html'
    context_object_name = 'users'
    login_url = 'login'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = UserListFilterForm()
        return context


class UserCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new user - placeholder view.
    """
    model = User
    form_class = CustomUserCreationForm
    template_name = 'core/user_form.html'
    success_url = reverse_lazy('user_list')
    login_url = 'login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Create'
        return context


class UserEditView(LoginRequiredMixin, UpdateView):
    """
    Edit an existing user - placeholder view.
    """
    model = User
    form_class = CustomUserChangeForm
    template_name = 'core/user_form.html'
    success_url = reverse_lazy('user_list')
    login_url = 'login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action'] = 'Edit'
        return context


class UserDeleteView(LoginRequiredMixin, DeleteView):
    """
    Delete a user - placeholder view.
    """
    model = User
    template_name = 'core/user_confirm_delete.html'
    success_url = reverse_lazy('user_list')
    login_url = 'login'

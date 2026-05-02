from django.urls import path, include
from django.shortcuts import redirect
from . import views

urlpatterns = [
    path('', lambda request: redirect('login')),

    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    
    # Role-specific dashboards
    path('admin/dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('engineering/dashboard/', views.EngineeringDashboardView.as_view(), name='engineering_dashboard'),
    path('engineering/dashboard/infrastructure/', include('apps.infrastructure.urls', namespace='engineering_projects')),
    path('mayor/dashboard/', views.MayorDashboardView.as_view(), name='mayor_dashboard'),
    path('mayor/dashboard/non-infrastructure/', include('apps.non_infrastructure.urls', namespace='mayor_projects')),
    
    # Legacy admin dashboard URL (redirect)
    path('admin-dashboard/', views.AdminDashboardView.as_view()),
    
    # User management (admin only)
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('users/<int:pk>/edit/', views.UserEditView.as_view(), name='user_edit'),
    path('users/<int:pk>/delete/', views.UserDeleteView.as_view(), name='user_delete'),
    path('users/<int:pk>/reset-password/', views.UserPasswordResetInitiateView.as_view(), name='user_initiate_password_reset'),
    path('users/<int:pk>/password-history/', views.UserPasswordHistoryView.as_view(), name='user_password_history'),
    path('password-history/', views.PasswordHistoryListView.as_view(), name='password_history_list'),
]
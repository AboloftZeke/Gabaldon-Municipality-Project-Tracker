from django.urls import path
from django.shortcuts import redirect
from . import views

urlpatterns = [
    path('', lambda request: redirect('login')),

    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('users/<int:pk>/edit/', views.UserEditView.as_view(), name='user_edit'),
    path('users/<int:pk>/delete/', views.UserDeleteView.as_view(), name='user_delete'),
    path('users/<int:pk>/reset-password/', views.UserPasswordResetInitiateView.as_view(), name='user_initiate_password_reset'),
    path('users/<int:pk>/password-history/', views.UserPasswordHistoryView.as_view(), name='user_password_history'),
    path('password-history/', views.PasswordHistoryListView.as_view(), name='password_history_list'),

    # Project URLs
    path('projects/dashboard/', views.ProjectDashboardView.as_view(), name='project_dashboard'),
    path('projects/', views.ProjectListView.as_view(), name='project_list'),
    path('projects/create/', views.ProjectCreateView.as_view(), name='project_create'),
    path('projects/<int:pk>/', views.ProjectDetailView.as_view(), name='project_detail'),
    path('projects/<int:pk>/edit/', views.ProjectEditView.as_view(), name='project_edit'),
    path('projects/<int:pk>/delete/', views.ProjectDeleteView.as_view(), name='project_delete'),
    path('projects/<int:pk>/publish/', views.ProjectPublishView.as_view(), name='project_publish'),
    
    # Admin review/approval URLs
    path('projects/review/list/', views.ProjectReviewListView.as_view(), name='project_review_list'),
    path('projects/<int:pk>/review/', views.ProjectReviewView.as_view(), name='project_review'),
]
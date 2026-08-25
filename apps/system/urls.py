from django.urls import path, include
from django.shortcuts import redirect
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from . import views
from . import gis_views
from . import publication_views

urlpatterns = [
    path('', lambda request: redirect('login')),
    path('dashboard/', views.PublicDashboardView.as_view(), name='public_dashboard'),
    path(
        'dashboard/infrastructure/<int:pk>/',
        views.PublicInfrastructureProjectDetailView.as_view(),
        name='public_infrastructure_project_detail',
    ),
    path(
        'dashboard/non-infrastructure/<int:pk>/',
        views.PublicNonInfrastructureProjectDetailView.as_view(),
        name='public_non_infrastructure_project_detail',
    ),

    path('login/', views.LoginView.as_view(), name='login'),
    path(
        'login/verify/',
        views.LoginOTPVerifyView.as_view(),
        name='login_otp_verify',
    ),
    path(
        'login/verify/resend/',
        views.LoginOTPResendView.as_view(),
        name='login_otp_resend',
    ),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path(
        'forgot-password/',
        auth_views.PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.txt',
            html_email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
            success_url=reverse_lazy('password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'forgot-password/sent/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='registration/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'reset-password/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/password_reset_confirm.html',
            success_url=reverse_lazy('password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset-password/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='registration/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),

    # Administrator publication review
    path('admin-dashboard/publications/', publication_views.PublicationReviewQueueView.as_view(), name='publication_review_queue'),
    path('admin-dashboard/publications/<int:revision_id>/', publication_views.PublicationRevisionDetailView.as_view(), name='publication_revision_detail'),
    path('admin-dashboard/publications/<int:revision_id>/review/', publication_views.PublicationRevisionReviewView.as_view(), name='publication_revision_review'),
    path('admin-dashboard/publications/<int:revision_id>/publish/', publication_views.PublicationRevisionPublishView.as_view(), name='publication_revision_publish'),
    path('admin-dashboard/publications/<int:revision_id>/archive/', publication_views.PublicationRevisionArchiveView.as_view(), name='publication_revision_archive'),

    # Role-specific dashboards
    # Use a non-conflicting path so Django's admin site (mounted at /admin/) isn't intercepted.
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('engineering/dashboard/', views.EngineeringDashboardView.as_view(), name='engineering_dashboard'),
    path('engineering/dashboard/infrastructure/', include(('apps.infrastructure.urls', 'infrastructure'), namespace='engineering_projects')),
    path('mayor/dashboard/', views.MayorDashboardView.as_view(), name='mayor_dashboard'),
    path('mayor/dashboard/non-infrastructure/', include(('apps.non_infrastructure.urls', 'non_infrastructure'), namespace='mayor_projects')),

    # GIS data endpoints
    path('gis/layers/projects.json', gis_views.projects_geojson, name='gis_projects_layer'),
    path('gis/layers/<str:layer_name>.json', gis_views.static_layer_geojson, name='gis_static_layer'),
    path('gis/projects/<int:project_id>/photos.json', gis_views.project_photos, name='gis_project_photos'),
    
    # Legacy admin dashboard URL (kept for compatibility)
    # The named `admin_dashboard` route above now points to `/admin-dashboard/` to avoid
    # clashing with Django's built-in admin which is mounted at `/admin/`.
    
    # User management (admin only)
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('users/create/confirm/', views.UserCreateConfirmView.as_view(), name='user_create_confirm'),
    path('users/<int:pk>/edit/', views.UserEditView.as_view(), name='user_edit'),
    path('users/<int:pk>/edit/confirm/', views.UserEditConfirmView.as_view(), name='user_edit_confirm'),
    path('users/<int:pk>/deactivate/', views.UserDeactivateView.as_view(), name='user_deactivate'),
    path('users/<int:pk>/activate/', views.UserActivateView.as_view(), name='user_activate'),
    path('password-change/', views.PasswordChangeView.as_view(),name='password_change'),
]


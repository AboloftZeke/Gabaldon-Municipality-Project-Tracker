from django.urls import path
from . import views

app_name = 'non_infrastructure'

urlpatterns = [
    path('dashboard/', views.NonInfrastructureProjectDashboardView.as_view(), name='non_infrastructure_project_dashboard'),
    path('', views.NonInfrastructureProjectListView.as_view(), name='non_infrastructure_project_list'),
    path('create/', views.NonInfrastructureProjectCreateView.as_view(), name='non_infrastructure_project_create'),
    path('<int:pk>/', views.NonInfrastructureProjectDetailView.as_view(), name='non_infrastructure_project_detail'),
    path('<int:pk>/edit/', views.NonInfrastructureProjectEditView.as_view(), name='non_infrastructure_project_update'),
    path('<int:pk>/operations/', views.NonInfrastructureOperationalUpdateView.as_view(), name='non_infrastructure_project_operations'),
    path('<int:pk>/progress-updates/create/', views.NonInfrastructureProgressUpdateCreateView.as_view(), name='non_infrastructure_progress_update_create'),
    path('<int:pk>/progress-updates/<int:update_pk>/', views.NonInfrastructureProgressUpdateDetailView.as_view(), name='non_infrastructure_progress_update_detail'),
    path('<int:pk>/progress-updates/<int:update_pk>/submit/', views.NonInfrastructureProgressUpdateSubmitView.as_view(), name='non_infrastructure_progress_update_submit'),
    path('<int:pk>/submit-for-review/', views.NonInfrastructureProjectSubmitForReviewView.as_view(), name='non_infrastructure_project_submit_for_review'),
    path('<int:pk>/delete/', views.NonInfrastructureProjectDeleteView.as_view(), name='non_infrastructure_project_delete'),
]

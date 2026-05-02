from django.urls import path
from . import views

app_name = 'non_infrastructure'

urlpatterns = [
    path('dashboard/', views.NonInfrastructureProjectDashboardView.as_view(), name='non_infrastructure_project_dashboard'),
    path('', views.NonInfrastructureProjectListView.as_view(), name='non_infrastructure_project_list'),
    path('create/', views.NonInfrastructureProjectCreateView.as_view(), name='non_infrastructure_project_create'),
    path('<int:pk>/', views.NonInfrastructureProjectDetailView.as_view(), name='non_infrastructure_project_detail'),
    path('<int:pk>/edit/', views.NonInfrastructureProjectEditView.as_view(), name='non_infrastructure_project_update'),
    path('<int:pk>/delete/', views.NonInfrastructureProjectDeleteView.as_view(), name='non_infrastructure_project_delete'),
]

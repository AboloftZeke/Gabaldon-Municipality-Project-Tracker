from django.urls import path
from . import views

app_name = 'infrastructure'

urlpatterns = [
    path('dashboard/', views.ProjectDashboardView.as_view(), name='project_dashboard'),
    path('', views.ProjectListView.as_view(), name='project_list'),
    path('create/', views.ProjectCreateView.as_view(), name='project_create'),
    path('<int:pk>/', views.ProjectDetailView.as_view(), name='project_detail'),
    path('<int:pk>/edit/', views.ProjectEditView.as_view(), name='project_update'),
    path('<int:pk>/operations/', views.InfrastructureOperationalUpdateView.as_view(), name='project_operations'),
    path('<int:pk>/inspections/add/', views.InfrastructureInspectionCreateView.as_view(), name='inspection_create'),
    path('<int:project_pk>/inspections/<int:inspection_pk>/edit/', views.InfrastructureInspectionUpdateView.as_view(), name='inspection_update'),
    path('<int:pk>/submit-for-review/', views.ProjectSubmitForReviewView.as_view(), name='project_submit_for_review'),
    path('<int:pk>/delete/', views.ProjectDeleteView.as_view(), name='project_delete'),
]

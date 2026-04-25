from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from .models import Project
from .forms import ProjectForm


@login_required
def project_list(request):
    """Display list of all infrastructure projects"""
    projects = Project.objects.all()
    context = {
        'projects': projects,
        'total_projects': projects.count(),
    }
    return render(request, 'projects/project_list.html', context)


@login_required
def project_detail(request, pk):
    """Display project details"""
    project = get_object_or_404(Project, pk=pk)
    context = {'project': project}
    return render(request, 'projects/project_detail.html', context)


@login_required
def project_create(request):
    """Create a new infrastructure project"""
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user
            project.save()
            return redirect('project_detail', pk=project.pk)
    else:
        form = ProjectForm()

    context = {'form': form, 'action': 'Create'}
    return render(request, 'projects/project_form.html', context)


@login_required
def project_update(request, pk):
    """Update an existing infrastructure project"""
    project = get_object_or_404(Project, pk=pk)

    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            return redirect('project_detail', pk=project.pk)
    else:
        form = ProjectForm(instance=project)

    context = {'form': form, 'action': 'Edit', 'project': project}
    return render(request, 'projects/project_form.html', context)


@login_required
def project_delete(request, pk):
    """Delete an infrastructure project"""
    project = get_object_or_404(Project, pk=pk)

    if request.method == 'POST':
        project.delete()
        return redirect('project_list')

    context = {'project': project}
    return render(request, 'projects/project_confirm_delete.html', context)

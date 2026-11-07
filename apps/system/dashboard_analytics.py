"""Office-scoped project analytics for staff and Head dashboards."""

from collections import Counter
from datetime import date

from django.db.models import Min
from django.utils import timezone

from .choices import BARANGAY_CHOICES
from .models import (
    InfrastructureProject,
    InfrastructureSchedule,
    NonInfrastructureProgressUpdate,
    NonInfrastructureProject,
    ProjectRevision,
)


STATUS_KEYS = ('ongoing', 'completed', 'delayed')


def _month_key(value):
    if hasattr(value, 'date'):
        value = timezone.localtime(value).date()
    return value.year, value.month


def _monthly_series(dates, *, through=None):
    counts = Counter(_month_key(value) for value in dates)
    if not counts:
        return {'labels': [], 'values': []}

    start = min(counts)
    end = max(counts)
    if through is not None:
        end = max(end, (through.year, through.month))

    labels = []
    values = []
    year, month = start
    while (year, month) <= end:
        labels.append(date(year, month, 1).strftime('%b %Y'))
        values.append(counts[(year, month)])
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return {'labels': labels, 'values': values}


def _publication_dates(project_type):
    subtype_filter = (
        {'project__infrastructure_project__isnull': False}
        if project_type == 'infrastructure'
        else {'project__non_infrastructure_project__isnull': False}
    )
    revisions = ProjectRevision.objects.filter(
        project__project_type=project_type,
        status__in=('published', 'archived'),
        **subtype_filter,
    )
    dates = list(
        revisions.filter(
            published_at__isnull=False,
        )
        .values('project_id')
        .annotate(first_published=Min('published_at'))
        .values_list('first_published', flat=True)
    )
    public_project_count = revisions.values('project_id').distinct().count()
    return dates, max(public_project_count - len(dates), 0)


def _project_records(project_type):
    if project_type == 'infrastructure':
        return list(
            InfrastructureProject.objects.filter(
                project__project_type='infrastructure',
            ).select_related('project', 'address').values(
                'infrastructure_id',
                'status',
                'planned_end_date',
                'address__barangay',
            )
        )
    return list(
        NonInfrastructureProject.objects.filter(
            project__project_type='non_infrastructure',
        ).select_related('project', 'address').values(
            'non_infra_id',
            'status',
            'implementation_end_date',
            'address__barangay',
        )
    )


def _status_and_barangay(records, project_type, today):
    status_counts = Counter({key: 0 for key in STATUS_KEYS})
    barangay_counts = Counter({code: 0 for code, _ in BARANGAY_CHOICES})
    barangay_keys = {}
    for code, label in BARANGAY_CHOICES:
        for value in (code, label, label.split(' (', 1)[0]):
            barangay_keys[value.strip().casefold()] = code
    barangay_keys['north poblacion'] = 'bitulok'

    end_date_key = (
        'planned_end_date'
        if project_type == 'infrastructure'
        else 'implementation_end_date'
    )
    status_project_count = 0
    for record in records:
        status_project_count += 1
        if record['status'] == 'completed':
            status_counts['completed'] += 1
        elif record[end_date_key] and record[end_date_key] < today:
            status_counts['delayed'] += 1
        else:
            status_counts['ongoing'] += 1

        barangay = (record['address__barangay'] or '').strip().casefold()
        code = barangay_keys.get(barangay)
        if code is None:
            code = barangay_keys.get(barangay.replace('_', ' '))
        if code:
            barangay_counts[code] += 1

    return (
        [
            {
                'key': key,
                'label': key.title(),
                'value': status_counts[key],
            }
            for key in STATUS_KEYS
        ],
        [
            {
                'key': code,
                'label': label,
                'value': barangay_counts[code],
            }
            for code, label in BARANGAY_CHOICES
        ],
        status_project_count,
    )


def _completion_dates(project_type):
    if project_type == 'infrastructure':
        completed_count = InfrastructureProject.objects.filter(
            project__project_type='infrastructure',
            status='completed',
        ).count()
        dated = list(
            InfrastructureSchedule.objects.filter(
                infrastructure__project__project_type='infrastructure',
                infrastructure__status='completed',
                actual_completion_date__isnull=False,
            )
            .values('infrastructure_id')
            .annotate(completed_on=Min('actual_completion_date'))
            .values_list('infrastructure_id', 'completed_on')
        )
        per_project = {}
        for project_id, completed_on in dated:
            per_project[project_id] = completed_on
        return list(per_project.values()), max(
            completed_count - len(per_project), 0,
        )

    completed_count = NonInfrastructureProject.objects.filter(
        project__project_type='non_infrastructure',
        status='completed',
    ).count()
    dated = list(
        NonInfrastructureProgressUpdate.objects.filter(
            non_infrastructure__project__project_type='non_infrastructure',
            non_infrastructure__status='completed',
            proposed_status='completed',
            review_status=NonInfrastructureProgressUpdate.ReviewStatus.APPROVED,
            applied_at__isnull=False,
        )
        .values('non_infrastructure_id')
        .annotate(completed_on=Min('applied_at'))
        .values_list('non_infrastructure_id', 'completed_on')
    )
    per_project = {}
    for project_id, completed_on in dated:
        per_project[project_id] = completed_on
    return list(per_project.values()), max(
        completed_count - len(per_project), 0,
    )


def project_analytics(project_type):
    """Build chart data exclusively from one office's authoritative records."""
    if project_type not in {'infrastructure', 'non_infrastructure'}:
        raise ValueError(f'Unsupported project type: {project_type}')

    today = timezone.localdate()
    records = _project_records(project_type)
    publication_dates, published_without_dates = _publication_dates(
        project_type,
    )
    statuses, barangays, project_count = _status_and_barangay(
        records,
        project_type,
        today,
    )
    completion_dates, completed_without_dates = _completion_dates(project_type)

    return {
        'published_by_month': _monthly_series(
            publication_dates,
            through=today,
        ),
        'published_without_dates': published_without_dates,
        'status': statuses,
        'status_project_count': project_count,
        'barangays': barangays,
        'completed_by_month': _monthly_series(completion_dates),
        'completed_without_dates': completed_without_dates,
        'completion_date_source': (
            'Actual completion date from the infrastructure schedule.'
            if project_type == 'infrastructure'
            else 'Approved progress-update application date for the completion transition.'
        ),
    }

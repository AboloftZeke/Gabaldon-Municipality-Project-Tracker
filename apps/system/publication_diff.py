"""Presentation-ready comparisons of retained publication snapshots.

Database IDs and capture timestamps are metadata, not project changes. Missing,
null and empty strings represent the same cleared value; zero remains a value.
"""

from decimal import Decimal, InvalidOperation


SECTIONS = (
    ('project', 'Publication Attribution'),
    ('infrastructure', 'Project Information'),
    ('non_infrastructure', 'Program Information'),
    ('financial', 'Funding'),
    ('schedule', 'Schedule'),
    ('inspection', 'Latest Inspection'),
)
IGNORED = {'id', 'schema_version', 'created_at', 'updated_at', 'cover_image_url'}
LABELS = {
    'creator': 'Published By Attribution', 'award_status': 'Status',
    'status': 'Status', 'procurement_method': 'Procurement Method',
    'inspected_by': 'Inspected By', 'duration_days': 'Duration (days)',
}
NUMERIC = {
    'approved_budget', 'contract_price', 'actual_expenditure', 'percentage',
    'cost_progress_percentage', 'physical_progress_percentage',
    'completion_percentage', 'latitude', 'longitude', 'beneficiaries',
    'duration_days',
}


def _empty(value):
    return value is None or value == '' or value == {} or value == []


def _normalized(value, key):
    if _empty(value):
        return None
    if isinstance(value, dict):
        return {k: _normalized(v, k) for k, v in value.items() if k not in IGNORED}
    if key in NUMERIC:
        try:
            return Decimal(str(value))
        except InvalidOperation:
            pass
    return value


def _display(value, key):
    if _empty(value):
        return 'Not provided'
    if isinstance(value, dict):
        name = value.get('display_name') or value.get('name') or value.get('username') or ''
        details = [str(value[k]) for k in ('code', 'username') if value.get(k) and value[k] != name]
        if not _empty(value.get('percentage')):
            details.append(f'{value["percentage"]}%')
        return f'{name} ({", ".join(details)})' if details else name
    if key in {'approved_budget', 'contract_price', 'actual_expenditure'}:
        try:
            return f'₱{Decimal(str(value)):,.2f}'
        except InvalidOperation:
            pass
    if key.endswith('percentage') or key == 'percentage':
        return f'{value}%'
    return str(value)


def _fields(before, after, prefix='', compare=True):
    rows = []
    for key in dict.fromkeys([*after, *before]):
        if key in IGNORED or key.endswith('_label'):
            continue
        old, new = before.get(key), after.get(key)
        label = LABELS.get(key, key.replace('_', ' ').title())
        path = f'{prefix}.{key}' if prefix else key
        # Named relationships are one field; address/funding structures expand.
        sample = new if isinstance(new, dict) and new else old
        if isinstance(sample, dict) and not any(k in sample for k in ('name', 'display_name', 'username')):
            rows.extend(_fields(old or {}, new or {}, path, compare))
            continue
        state = 'unchanged'
        if compare and _normalized(old, key) != _normalized(new, key):
            state = 'added' if _empty(old) else 'removed' if _empty(new) else 'modified'
        rows.append({
            'path': path,
            'label': f'{prefix.replace("_", " ").title()} · {label}' if prefix else label,
            'before': _display(before.get(f'{key}_label') or old, key),
            'after': _display(after.get(f'{key}_label') or new, key),
            'state': state, 'changed': state != 'unchanged',
            'badge': {'modified': 'Changed', 'added': 'Added', 'removed': 'Removed'}.get(state, ''),
        })
    return rows


def compare_snapshots(submitted, published=None):
    """Compare content only. None means no baseline, including first submissions."""
    submitted, baseline = submitted or {}, published or {}
    sections = []
    for key, label in SECTIONS:
        old, new = baseline.get(key) or {}, submitted.get(key) or {}
        rows = _fields(old, new, compare=published is not None)
        if rows:
            sections.append({'label': label, 'fields': rows, 'changed': any(r['changed'] for r in rows)})
    images = []
    old_images = list(baseline.get('images') or [])
    for new in submitted.get('images') or []:
        old = next((item for item in old_images if (
            new.get('id') is not None and item.get('id') == new['id']
        ) or (new.get('url') and item.get('url') == new['url'])), None)
        if old is not None:
            old_images.remove(old)
        state = 'unchanged'
        if published is not None:
            state = 'added' if old is None else 'modified' if (
                old.get('url') != new.get('url') or bool(old.get('is_cover')) != bool(new.get('is_cover'))
            ) else 'unchanged'
        images.append({'before': old, 'after': new, 'state': state, 'changed': state != 'unchanged'})
    if published is not None:
        images.extend({'before': old, 'after': None, 'state': 'removed', 'changed': True} for old in old_images)
    return {
        'sections': sections, 'images': images,
        'images_changed': any(row['changed'] for row in images),
        'change_count': sum(row['changed'] for section in sections for row in section['fields']) + sum(row['changed'] for row in images),
    }

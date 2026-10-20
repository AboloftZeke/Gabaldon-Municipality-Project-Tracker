"""Report identity and media selected without consulting live project evidence."""

from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import PermissionDenied


def report_preparer(user):
    if not user or not user.is_authenticated:
        raise PermissionDenied('An authenticated report preparer is required.')
    assignment = getattr(user, 'role_assignment', None)
    position = ''
    if assignment:
        position = ' · '.join(filter(None, (
            assignment.get_role_display(), assignment.get_department_display(),
        )))
    elif user.is_superuser:
        position = 'Administrator'
    return {
        'name': user.get_full_name().strip() or user.get_username(),
        'position': position,
    }


def disclosed_evidence_images(report_type, snapshot):
    """Only evidence frozen into this published revision is eligible.

    Infrastructure uses the Head's selected supporting inspections. Mayor
    evidence additionally requires the retained update to be approved.
    Never query live inspection/evidence tables or fetch arbitrary URLs.
    """
    images = []
    if report_type == 'infrastructure':
        update = snapshot.get('progress_update') or {}
        for inspection in update.get('supporting_inspections') or []:
            for evidence in inspection.get('evidence') or []:
                if evidence.get('type') != 'image':
                    continue
                url = evidence.get('url') or ''
                if not _safe_media_url(url):
                    continue
                images.append({
                    'image_url': url,
                    'caption': f"Inspection {inspection.get('inspection_date') or ''}: "
                    f"{evidence.get('original_name') or 'Supporting image'}",
                })
    else:
        update = snapshot.get('non_infrastructure_progress_update') or {}
        if update.get('review_status') != 'approved':
            return []
        for evidence in update.get('evidence') or []:
            path = evidence.get('file_path') or ''
            parts = PurePosixPath(path).parts
            if (
                len(parts) < 3 or parts[:2] != ('non_infrastructure', 'evidence')
                or '..' in parts or '\\' in path
                or PurePosixPath(path).suffix.lower() not in IMAGE_EXTENSIONS
            ):
                continue
            images.append({
                'image_url': f'{settings.MEDIA_URL.rstrip("/")}/{path}',
                'caption': evidence.get('description') or parts[-1],
            })
    return images


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


def _safe_media_url(url):
    prefix = settings.MEDIA_URL or '/media/'
    if not isinstance(url, str) or not url.startswith(prefix):
        return False
    path = url[len(prefix):]
    return bool(
        path and not path.startswith('/') and '\\' not in path
        and '..' not in PurePosixPath(path).parts
        and PurePosixPath(path).suffix.lower() in IMAGE_EXTENSIONS
    )

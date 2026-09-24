"""Display helpers for internal Mayor evidence pages."""

from pathlib import PurePosixPath

from django import template


register = template.Library()


@register.filter
def evidence_filename(path):
    return PurePosixPath(str(path or '')).name or 'Supporting file'


@register.filter
def evidence_extension(path):
    return PurePosixPath(str(path or '')).suffix.lower().lstrip('.')

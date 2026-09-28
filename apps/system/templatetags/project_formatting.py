from django import template

from apps.system.formatting import format_barangay, format_peso


register = template.Library()


@register.filter
def peso(value):
    return format_peso(value)


@register.filter
def barangay_label(value):
    return format_barangay(value)

from django import template

register = template.Library()

@register.filter
def to(start, end):
    return range(start, end)

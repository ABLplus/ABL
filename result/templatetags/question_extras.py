from django import template

register = template.Library()

@register.filter
def get_option(question, key):
    key = key.lower()
    return getattr(question, f'option_{key}', '')

import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name='render_markdown', is_safe=True)
def render_markdown(value: str) -> str:
    """
    Convert a Markdown string to HTML and mark it safe for rendering.
    Usage in templates: {{ text|render_markdown }}
    """
    if not value:
        return ''
    # You can add or remove extensions as needed
    html = markdown.markdown(
        value,
        extensions=[
            'extra',        # tables, footnotes, etc.
            'smarty',       # smart quotes, dashes
            'codehilite',   # syntax highlighting
        ]
    )
    return mark_safe(html)

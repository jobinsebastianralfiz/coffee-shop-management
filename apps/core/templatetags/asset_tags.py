"""
{% static_v 'css/theme.css' %} -> /static/css/theme.css?v=<last-modified>

Browsers cache static files; a version tied to the file's modification time
makes them fetch the new copy as soon as the file changes, without anyone
having to remember to bump a number by hand.
"""

import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    url = static(path)
    found = finders.find(path)
    if not found:
        return url
    try:
        version = int(os.path.getmtime(found))
    except OSError:
        return url
    return f"{url}{'&' if '?' in url else '?'}v={version}"

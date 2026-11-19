"""Attributs de présentation pour les images des contenus publics administrés."""
import re
from html.parser import HTMLParser

from django import template
from django.utils.html import escape

register = template.Library()
IMAGE = re.compile(r"<img\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", re.I)


class ImageTag(HTMLParser):
    def handle_starttag(self, tag, attrs):
        self.attrs = dict(attrs)


@register.filter
def public_image_attributes(value, description="Illustration — UFHOB-Mali"):
    # Ces contenus sont déjà rendus comme HTML par les templates concernés.
    # Seules les balises image sont modifiées, sans réécrire les autres éléments.
    def replace(match):
        parser = ImageTag()
        parser.feed(match.group(0))
        attrs = parser.attrs
        if not attrs.get("alt", "").strip():
            attrs["alt"] = str(description)
        attrs.setdefault("width", "1200")
        attrs.setdefault("height", "800")
        attrs["loading"] = "lazy"
        return "<img " + " ".join(
            name if val is None else f'{name}="{escape(val)}"'
            for name, val in attrs.items()
        ) + ">"
    return IMAGE.sub(replace, str(value or ""))

"""Gestionnaires pouvant encaisser un dossier (école + campus)."""

from django import template

from payments.services.cash import eligible_agents_for_inscription

register = template.Library()


@register.simple_tag
def eligible_payment_agents(inscription):
    return list(eligible_agents_for_inscription(inscription))

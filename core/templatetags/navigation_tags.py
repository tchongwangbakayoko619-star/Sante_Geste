"""Balises et filtres de navigation pour SantéGeste (Fil d'Ariane / Breadcrumbs)."""

from __future__ import annotations

from typing import Any

from django import template
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

register = template.Library()


def _safe_reverse(viewname: str, *args, **kwargs) -> str | None:
    try:
        return reverse(viewname, args=args, kwargs=kwargs)
    except NoReverseMatch:
        return None


def resolve_breadcrumbs(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not context or 'request' not in context:
        return []

    request = context['request']
    resolver_match = getattr(request, 'resolver_match', None)
    if not resolver_match:
        return []

    url_name = resolver_match.url_name or ''
    app_name = resolver_match.app_name or ''
    view_name = resolver_match.view_name or ''
    kwargs = resolver_match.kwargs or {}

    home_url = _safe_reverse('home') or '/'
    root_crumb = {'label': _('Accueil'), 'url': home_url, 'active': False}

    if view_name in ('home', 'dashboard:home') or url_name == 'home':
        return [{'label': _('Accueil'), 'url': None, 'active': True}]

    crumbs: list[dict[str, Any]] = [root_crumb]

    patient = context.get('patient') or context.get('object')
    patient_name = ''
    patient_url = None
    if patient and hasattr(patient, 'full_name'):
        patient_name = str(patient.full_name)
        if hasattr(patient, 'get_absolute_url'):
            try:
                patient_url = patient.get_absolute_url()
            except Exception:
                patient_url = None

    if app_name == 'patients' or view_name.startswith('patients:'):
        patients_list_url = _safe_reverse('patients:patient_list')
        appointments_list_url = _safe_reverse('patients:appointment_list')

        if url_name in ('appointment_list', 'appointment_create', 'appointment_status_update', 'appointment_cancel'):
            crumbs.append({'label': _('Rendez-vous'), 'url': appointments_list_url, 'active': False})

            if url_name == 'appointment_list':
                crumbs.append({'label': _('Agenda complet'), 'url': None, 'active': True})
            elif url_name == 'appointment_create':
                crumbs.append({'label': _('Planifier un RDV'), 'url': None, 'active': True})
            elif url_name == 'appointment_status_update':
                crumbs.append({'label': _('Statut rendez-vous'), 'url': None, 'active': True})
            elif url_name == 'appointment_cancel':
                crumbs.append({'label': _('Annuler un rendez-vous'), 'url': None, 'active': True})
        else:
            crumbs.append({'label': _('Gestion Patients'), 'url': patients_list_url, 'active': False})

            if url_name == 'patient_list':
                crumbs.append({'label': _('Dossiers patients'), 'url': None, 'active': True})
            elif url_name == 'patient_create':
                crumbs.append({'label': _('Nouveau patient'), 'url': None, 'active': True})
            elif url_name == 'patient_detail':
                label = patient_name or _('Fiche patient')
                crumbs.append({'label': label, 'url': None, 'active': True})
            elif url_name == 'patient_update':
                label = patient_name or _('Patient')
                crumbs.append({'label': label, 'url': patient_url, 'active': False})
                crumbs.append({'label': _('Modifier'), 'url': None, 'active': True})
            elif url_name == 'patient_medical_update':
                label = patient_name or _('Patient')
                crumbs.append({'label': label, 'url': patient_url, 'active': False})
                crumbs.append({'label': _('Dossier médical'), 'url': None, 'active': True})
            elif url_name == 'patient_allergy_create':
                label = patient_name or _('Patient')
                crumbs.append({'label': label, 'url': patient_url, 'active': False})
                medical_url = _safe_reverse('patients:patient_medical_update', pk=kwargs.get('pk'))
                crumbs.append({'label': _('Dossier médical'), 'url': medical_url, 'active': False})
                crumbs.append({'label': _('Ajouter allergie'), 'url': None, 'active': True})
            elif url_name == 'patient_allergy_delete':
                label = patient_name or _('Patient')
                crumbs.append({'label': label, 'url': patient_url, 'active': False})
                crumbs.append({'label': _('Supprimer allergie'), 'url': None, 'active': True})
            else:
                fallback_label = url_name.replace('_', ' ').title()
                crumbs.append({'label': fallback_label, 'url': None, 'active': True})

    elif app_name == 'users' or view_name.startswith('users:'):
        profile_url = _safe_reverse('users:profile')

        if url_name in ('profile', 'profile-edit', 'medical-profile-edit', 'change-password'):
            crumbs.append({'label': _('Mon Espace'), 'url': profile_url, 'active': False})

            if url_name == 'profile':
                crumbs.append({'label': _('Mon Profil'), 'url': None, 'active': True})
            elif url_name == 'profile-edit':
                crumbs.append({'label': _('Mon Profil'), 'url': profile_url, 'active': False})
                crumbs.append({'label': _('Modifier'), 'url': None, 'active': True})
            elif url_name == 'medical-profile-edit':
                crumbs.append({'label': _('Mon Profil'), 'url': profile_url, 'active': False})
                crumbs.append({'label': _('Profil médical'), 'url': None, 'active': True})
            elif url_name == 'change-password':
                crumbs.append({'label': _('Sécurité'), 'url': profile_url, 'active': False})
                crumbs.append({'label': _('Changer mot de passe'), 'url': None, 'active': True})
        else:
            fallback_label = url_name.replace('_', ' ').replace('-', ' ').title()
            crumbs.append({'label': fallback_label, 'url': None, 'active': True})

    elif url_name == 'about':
        crumbs.append({'label': _('À propos'), 'url': None, 'active': True})

    else:
        label = url_name.replace('_', ' ').replace('-', ' ').title() or _('Page')
        crumbs.append({'label': label, 'url': None, 'active': True})

    if crumbs:
        for c in crumbs[:-1]:
            c['active'] = False
        crumbs[-1]['active'] = True

    return crumbs


@register.simple_tag(takes_context=True)
def get_breadcrumbs(
    context: template.Context,
    custom_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if custom_items is not None and isinstance(custom_items, list):
        return custom_items
    custom = context.get('breadcrumbs') or context.get('breadcrumb_items')
    if custom and isinstance(custom, list):
        return custom
    return resolve_breadcrumbs(context.flatten())


@register.inclusion_tag('components/molecules/nav/breadcrumbs.html', takes_context=True)
def render_breadcrumbs(context: template.Context, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if items is None:
        items = get_breadcrumbs(context)
    return {
        'items': items,
        'request': context.get('request'),
    }

"""Tests unitaires pour le composant de navigation Fil d'Ariane (Breadcrumbs)."""

import pytest
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import resolve

from core.templatetags.navigation_tags import get_breadcrumbs, resolve_breadcrumbs


def render_template(template_str: str, context_dict: dict = None) -> str:
    template = Template(template_str)
    context = Context(context_dict or {})
    return template.render(context)


@pytest.fixture
def rf():
    return RequestFactory()


def test_resolve_breadcrumbs_empty_context():
    assert resolve_breadcrumbs({}) == []
    assert resolve_breadcrumbs(None) == []


def test_resolve_breadcrumbs_home(rf):
    request = rf.get('/')
    request.resolver_match = resolve('/')
    context = {'request': request}

    crumbs = resolve_breadcrumbs(context)
    assert len(crumbs) == 1
    assert crumbs[0]['label'] == 'Accueil'
    assert crumbs[0]['active'] is True


def test_resolve_breadcrumbs_patient_list(rf):
    request = rf.get('/patients/')
    request.resolver_match = resolve('/patients/')
    context = {'request': request}

    crumbs = resolve_breadcrumbs(context)
    assert len(crumbs) == 3
    assert crumbs[0]['label'] == 'Accueil'
    assert crumbs[1]['label'] == 'Gestion Patients'
    assert crumbs[2]['label'] == 'Dossiers patients'
    assert crumbs[2]['active'] is True


def test_resolve_breadcrumbs_patient_create(rf):
    request = rf.get('/patients/nouveau/')
    request.resolver_match = resolve('/patients/nouveau/')
    context = {'request': request}

    crumbs = resolve_breadcrumbs(context)
    assert len(crumbs) == 3
    assert crumbs[0]['label'] == 'Accueil'
    assert crumbs[1]['label'] == 'Gestion Patients'
    assert crumbs[2]['label'] == 'Nouveau patient'
    assert crumbs[2]['active'] is True


def test_resolve_breadcrumbs_appointments_list(rf):
    request = rf.get('/patients/rendez-vous/')
    request.resolver_match = resolve('/patients/rendez-vous/')
    context = {'request': request}

    crumbs = resolve_breadcrumbs(context)
    assert len(crumbs) == 3
    assert crumbs[0]['label'] == 'Accueil'
    assert crumbs[1]['label'] == 'Rendez-vous'
    assert crumbs[2]['label'] == 'Agenda complet'


def test_resolve_breadcrumbs_appointments_today(rf):
    request = rf.get('/patients/rendez-vous/?date_filter=today')
    request.resolver_match = resolve('/patients/rendez-vous/')
    context = {'request': request}

    crumbs = resolve_breadcrumbs(context)
    assert len(crumbs) == 3
    assert crumbs[0]['label'] == 'Accueil'
    assert crumbs[1]['label'] == 'Rendez-vous'
    assert crumbs[2]['label'] == 'Agenda complet'


def test_resolve_breadcrumbs_profile(rf):
    request = rf.get('/users/profile/')
    request.resolver_match = resolve('/users/profile/')
    context = {'request': request}

    crumbs = resolve_breadcrumbs(context)
    assert len(crumbs) == 3
    assert crumbs[0]['label'] == 'Accueil'
    assert crumbs[1]['label'] == 'Mon Espace'
    assert crumbs[2]['label'] == 'Mon Profil'


def test_resolve_breadcrumbs_profile_edit(rf):
    request = rf.get('/users/profile/edit/')
    request.resolver_match = resolve('/users/profile/edit/')
    context = {'request': request}

    crumbs = resolve_breadcrumbs(context)
    assert len(crumbs) == 4
    assert crumbs[0]['label'] == 'Accueil'
    assert crumbs[1]['label'] == 'Mon Espace'
    assert crumbs[2]['label'] == 'Mon Profil'
    assert crumbs[3]['label'] == 'Modifier'
    assert crumbs[3]['active'] is True


def test_render_breadcrumbs_molecule_with_custom_items():
    custom_items = [
        {'label': 'Accueil', 'url': '/', 'active': False},
        {'label': 'Gestion', 'url': '/gestion/', 'active': False},
        {'label': 'Personnel', 'url': None, 'active': True},
    ]

    html = render_template(
        '{% load navigation_tags %}'
        '{% include "components/molecules/nav/breadcrumbs.html" with items=custom_items %}',
        {'custom_items': custom_items},
    )

    assert 'aria-label="Fil d\'Ariane"' in html
    assert 'Accueil' in html
    assert 'Gestion' in html
    assert 'Personnel' in html
    assert 'href="/"' in html
    assert 'href="/gestion/"' in html
    assert 'aria-current="page"' in html


def test_render_breadcrumbs_molecule_auto_resolution(rf):
    request = rf.get('/patients/')
    request.resolver_match = resolve('/patients/')

    html = render_template(
        '{% load navigation_tags %}'
        '{% include "components/molecules/nav/breadcrumbs.html" %}',
        {'request': request},
    )

    assert 'aria-label="Fil d\'Ariane"' in html
    assert 'Accueil' in html
    assert 'Gestion Patients' in html
    assert 'Dossiers patients' in html


@pytest.mark.django_db
def test_patient_list_view_contains_breadcrumbs(client, django_user_model):
    user = django_user_model.objects.create_user(
        email='test_user@example.com',
        password='ValidPassword123!',
        is_active=True,
        is_agent_accueil=True,
    )
    client.force_login(user)

    response = client.get('/patients/')
    assert response.status_code == 200
    content = response.content.decode('utf-8')

    assert 'aria-label="Fil d\'Ariane"' in content
    assert 'Accueil' in content
    assert 'Gestion Patients' in content
    assert 'Dossiers patients' in content

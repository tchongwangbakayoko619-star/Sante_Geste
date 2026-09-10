"""Tests unitaires pour le composant Molecule Alert et Flash Messages (CS² Health Design System)."""

import pytest
from django.template import Context, Template


def render_template(template_str: str, context_dict: dict = None) -> str:
    template = Template(template_str)
    context = Context(context_dict or {})
    return template.render(context)


@pytest.mark.parametrize(
    "variant,expected_bg,expected_border,expected_text,expected_icon",
    [
        ("success", "bg-emerald-950", "border-emerald-400", "text-emerald-200", "m4.5 12.75 6 6 9-13.5"),
        ("warning", "bg-amber-950", "border-yellow-400", "text-yellow-200", "M12 9v3.75"),
        ("error", "bg-red-950", "border-red-500", "text-red-200", "M9.75 9.75l4.5 4.5"),
        ("danger", "bg-red-950", "border-red-500", "text-red-200", "M9.75 9.75l4.5 4.5"),
        ("info", "bg-slate-900", "border-blue-500", "text-blue-200", "M11.25 11.25"),
    ],
)
def test_alert_molecule_variants(variant, expected_bg, expected_border, expected_text, expected_icon):
    html = render_template(
        '{% include "components/molecules/alert.html" with variant=variant message="Ceci est un test" %}',
        {"variant": variant},
    )
    assert expected_bg in html
    assert "border-l-4" in html
    assert expected_border in html
    assert expected_text in html
    assert expected_icon in html
    assert "Ceci est un test" in html
    assert 'role="alert"' in html


def test_alert_molecule_with_empty_context():
    html = render_template(
        '{% include "components/molecules/alert.html" %}',
        {},
    )
    assert "bg-slate-900" in html
    assert "border-blue-500" in html
    assert "text-blue-200" in html


def test_alert_molecule_dismissible():
    html = render_template(
        '{% include "components/molecules/alert.html" with variant="warning" message="Attendez 60s" dismissible=True %}'
    )
    assert "data-alert-close" in html
    assert "Attendez 60s" in html


def test_alert_molecule_auto_dismiss():
    html = render_template(
        '{% include "components/molecules/alert.html" with variant="warning" message="Attendez 60s" auto_dismiss=5000 %}'
    )
    assert 'data-auto-dismiss="5000"' in html
    assert "flash-alert-progress-bar" in html

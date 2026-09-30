"""Tests unitaires pour les icônes des cartes KPI et le composant Stat Card."""

import html as html_lib
import pytest
from django.template import Context, Template


def render_template(template_str: str, context_dict: dict = None) -> str:
    template = Template(template_str)
    context = Context(context_dict or {})
    return template.render(context)


@pytest.mark.parametrize(
    "icon_name",
    [
        "check-circle",
        "user-plus",
        "stethoscope",
        "users",
        "user",
        "calendar",
        "clock",
        "x-mark",
        "trend-up",
        "trend-down",
    ],
)
def test_kpi_icons_rendered_in_icon_atom(icon_name):
    """Vérifie que chaque icône KPI est correctement définie et renvoie un SVG."""
    html = render_template(
        '{% include "components/atoms/icon.html" with name=icon_name size="w-6 h-6" %}',
        {"icon_name": icon_name},
    )
    assert "<svg" in html
    assert "</svg>" in html
    assert "w-6 h-6" in html


@pytest.mark.parametrize(
    "icon_name,variant,title,value",
    [
        ("users", "neutral", "Total dossiers", 120),
        ("check-circle", "primary", "Dossiers actifs", 115),
        ("user-plus", "blue", "Nouveaux (30 jours)", 8),
        ("calendar", "neutral", "Aujourd'hui", 14),
        ("clock", "amber", "En salle d'attente", 3),
        ("stethoscope", "purple", "En consultation", 2),
        ("check-circle", "primary", "Honorés / Terminés", 9),
    ],
)
def test_stat_card_molecule_renders_with_kpi_icon(icon_name, variant, title, value):
    """Vérifie que la carte Stat Card (KPI) inclut l'icône correspondante dans son conteneur."""
    html = render_template(
        '{% include "components/molecules/stat_items/stat_card.html" with title=title value=value icon_name=icon_name variant=variant %}',
        {
            "icon_name": icon_name,
            "variant": variant,
            "title": title,
            "value": value,
        },
    )
    unescaped_html = html_lib.unescape(html)
    assert title in unescaped_html
    assert str(value) in unescaped_html
    assert "<svg" in html
    assert "</svg>" in html


def test_dashboard_kpi_cards_grid_renders_all_icons():
    """Vérifie que le grid de 4 cartes KPI du dashboard affiche les 4 icônes principales et les indicateurs."""
    context = {
        "rdv_today_count": 12,
        "rdv_confirmed_count": 8,
        "total_patients": 150,
        "new_patients_period": 5,
        "rdv_upcoming_count": 4,
        "rdv_cancelled_count": 1,
        "period_filter": "today",
    }
    html = render_template(
        '{% include "components/organisms/dashboards/kpi_cards_grid.html" %}',
        context,
    )
    # Vérifie la présence des 4 cartes et valeurs
    assert "12" in html
    assert "150" in html
    assert "4" in html
    assert "1" in html
    # Vérifie que les SVG sont bien inclus
    svg_count = html.count("<svg")
    # 4 cartes principales + 4 indicateurs de tendance = 8 SVG
    assert svg_count >= 8

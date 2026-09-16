"""Formulaires de création et d'édition des dossiers patients."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.patients.models import Patient
from utils.phone import validate_phone_number


class PatientForm(forms.ModelForm):
    """Formulaire complet d'enregistrement et d'édition de dossier patient."""

    phone_number = forms.CharField(
        label=_("Téléphone"),
        max_length=20,
        required=True,
        validators=[validate_phone_number],
        widget=forms.TextInput(
            attrs={
                "placeholder": "+225 07 00 00 00 00",
                "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors",
            }
        ),
    )

    class Meta:
        model = Patient
        fields = [
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "blood_group",
            "phone_number",
            "email",
            "profession",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relation",
            "allergies",
            "chronic_diseases",
        ]
        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "placeholder": _("Ex: Jean-Marc"),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "placeholder": _("Ex: KOUASSI"),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors",
                }
            ),
            "date_of_birth": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors",
                }
            ),
            "gender": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors bg-white",
                }
            ),
            "blood_group": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors bg-white",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": _("patient@example.com"),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors",
                }
            ),
            "profession": forms.TextInput(
                attrs={
                    "placeholder": _("Ex: Enseignant, Commerçant..."),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors",
                }
            ),
            "address": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": _("Commune, quartier, repère..."),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors resize-none",
                }
            ),
            "emergency_contact_name": forms.TextInput(
                attrs={
                    "placeholder": _("Nom et prénom du proche"),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors",
                }
            ),
            "emergency_contact_phone": forms.TextInput(
                attrs={
                    "placeholder": _("Numéro joignable 24h/24"),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors",
                }
            ),
            "emergency_contact_relation": forms.TextInput(
                attrs={
                    "placeholder": _("Ex: Époux/se, Parent, Frère..."),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors",
                }
            ),
            "allergies": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("Ex: Pénicilline, Aspirine, Arachides... Laisser vide si aucune"),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-amber-300 bg-amber-50/20 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 text-sm text-neutral-800 transition-colors resize-none",
                }
            ),
            "chronic_diseases": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("Ex: Diabète type 2, HTA, Asthme... Laisser vide si aucune"),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-rose-300 bg-rose-50/20 focus:outline-none focus:ring-2 focus:ring-rose-500 focus:border-rose-500 text-sm text-neutral-800 transition-colors resize-none",
                }
            ),
        }


class PatientSearchForm(forms.Form):
    """Formulaire de filtrage et recherche instantanée de patients."""

    q = forms.CharField(
        required=False,
        label=_("Recherche"),
        widget=forms.TextInput(
            attrs={
                "placeholder": _("Rechercher un dossier par matricule, nom, prénom, téléphone..."),
                "class": "w-full pl-11 pr-4 py-2.5 rounded-2xl border border-neutral-200 bg-white text-sm placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-transparent transition-all shadow-xs",
                "autocomplete": "off",
            }
        ),
    )


class PatientMedicalUpdateForm(forms.ModelForm):
    """Formulaire réservé au personnel soignant pour la mise à jour des données cliniques."""

    class Meta:
        model = Patient
        fields = [
            "blood_group",
            "allergies",
            "chronic_diseases",
        ]
        widgets = {
            "blood_group": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors bg-white",
                }
            ),
            "allergies": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": _("Ex: Pénicilline, Sulfamides, Latex... Laisser vide si aucune allergie constatée"),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-amber-300 bg-amber-50/20 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 text-sm text-neutral-800 transition-colors resize-none",
                }
            ),
            "chronic_diseases": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": _("Ex: Diabète type 2 insulino-dépendant, HTA sous traitement, Asthme sévère..."),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-rose-300 bg-rose-50/20 focus:outline-none focus:ring-2 focus:ring-rose-500 focus:border-rose-500 text-sm text-neutral-800 transition-colors resize-none",
                }
            ),
        }



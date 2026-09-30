"""Formulaires de création et d'édition des dossiers patients."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.patients.models import Allergen
from apps.patients.models import Patient
from apps.patients.models import PatientAllergy
from utils.enums import PatientStatusEnum
from utils.phone import normalize_phone_number
from utils.phone import validate_phone_number


class PatientForm(forms.ModelForm):
    """Formulaire complet d'enregistrement et d'édition de dossier patient."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if "status" in self.fields:
            self.fields["status"].required = False
            self.fields["status"].initial = PatientStatusEnum.ACTIVE

    def clean_phone_number(self) -> str:
        phone = self.cleaned_data.get("phone_number", "")
        if phone:
            return normalize_phone_number(phone)
        return phone

    def clean_emergency_contact_phone(self) -> str:
        phone = self.cleaned_data.get("emergency_contact_phone", "")
        if phone:
            return normalize_phone_number(phone)
        return phone

    phone_number = forms.CharField(
        label=_("Téléphone"),
        max_length=20,
        required=True,
        validators=[validate_phone_number],
        widget=forms.TextInput(
            attrs={
                "type": "tel",
                "placeholder": "+225 07 00 00 00 00",
            }
        ),
    )
    emergency_contact_phone = forms.CharField(
        label=_("Téléphone du contact d'urgence"),
        max_length=20,
        required=False,
        validators=[validate_phone_number],
        widget=forms.TextInput(
            attrs={
                "type": "tel",
                "placeholder": _("Numéro joignable 24h/24"),
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
            "status",
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
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "placeholder": _("Ex: KOUASSI"),
                }
            ),
            "date_of_birth": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
            "gender": forms.Select(),
            "blood_group": forms.Select(),
            "status": forms.Select(),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": _("patient@example.com"),
                }
            ),
            "profession": forms.TextInput(
                attrs={
                    "placeholder": _("Ex: Enseignant, Commerçant..."),
                }
            ),
            "address": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": _("Commune, quartier, repère..."),
                    "class": "resize-none",
                }
            ),
            "emergency_contact_name": forms.TextInput(
                attrs={
                    "placeholder": _("Nom et prénom du proche"),
                }
            ),
            "emergency_contact_relation": forms.TextInput(
                attrs={
                    "placeholder": _("Ex: Époux/se, Parent, Frère..."),
                }
            ),
            "allergies": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("Ex: Pénicilline, Aspirine, Arachides... Laisser vide si aucune"),
                    "class": "border-amber-300 bg-amber-50/20 focus:ring-amber-500 focus:border-amber-500 resize-none",
                }
            ),
            "chronic_diseases": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("Ex: Diabète type 2, HTA, Asthme... Laisser vide si aucune"),
                    "class": "border-rose-300 bg-rose-50/20 focus:ring-rose-500 focus:border-rose-500 resize-none",
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
                "type": "search",
                "placeholder": _("Rechercher un dossier par matricule, nom, prénom, téléphone..."),
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
            "blood_group": forms.Select(),
            "allergies": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": _("Ex: Pénicilline, Sulfamides, Latex... Laisser vide si aucune allergie constatée"),
                    "class": "border-amber-300 bg-amber-50/20 focus:ring-amber-500 focus:border-amber-500 resize-none",
                }
            ),
            "chronic_diseases": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": _("Ex: Diabète type 2 insulino-dépendant, HTA sous traitement, Asthme sévère..."),
                    "class": "border-rose-300 bg-rose-50/20 focus:ring-rose-500 focus:border-rose-500 resize-none",
                }
            ),
        }


class PatientAllergyForm(forms.ModelForm):
    """Formulaire d'enregistrement d'une allergie codifiée pour un patient."""

    class Meta:
        model = PatientAllergy
        fields = [
            "allergen",
            "criticality",
            "verification_status",
            "reaction",
            "diagnosed_date",
            "notes",
        ]
        widgets = {
            "allergen": forms.Select(),
            "criticality": forms.Select(),
            "verification_status": forms.Select(),
            "reaction": forms.TextInput(
                attrs={
                    "placeholder": _("Ex: Œdème de Quincke, Urticaire aiguë, Choc anaphylactique..."),
                }
            ),
            "diagnosed_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("Précisions contextuelles, circonstances de survenue..."),
                    "class": "resize-none",
                }
            ),
        }




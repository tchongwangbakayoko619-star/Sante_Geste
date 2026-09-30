"""Formulaires pour la saisie des consultations, prestations, ordonnances et actes de caisse."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.patients.models import Consultation
from apps.patients.models import Facture
from apps.patients.models import LigneOrdonnance
from apps.patients.models import Ordonnance
from apps.patients.models import Paiement
from apps.patients.models import Prestation
from apps.patients.models import PrestationRealisee


class ConsultationForm(forms.ModelForm):
    """Formulaire d'enregistrement d'une consultation médicale."""

    tension = forms.CharField(
        label=_("Tension artérielle (ex: 12/8)"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "12/8"}),
    )
    poids = forms.CharField(
        label=_("Poids (kg)"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "70"}),
    )
    temperature = forms.CharField(
        label=_("Température (°C)"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "37.2"}),
    )
    pouls = forms.CharField(
        label=_("Fréquence cardiaque / Pouls (bpm)"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "75"}),
    )

    class Meta:
        model = Consultation
        fields = [
            "reason",
            "symptoms",
            "diagnosis",
            "notes",
            "status",
        ]
        widgets = {
            "reason": forms.TextInput(
                attrs={
                    "placeholder": _("Motif de la consultation..."),
                }
            ),
            "symptoms": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("Description détaillée des symptômes et constatations..."),
                    "class": "resize-none",
                }
            ),
            "diagnosis": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("Diagnostic clinique retenu..."),
                    "class": "resize-none",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": _("Notes confidentielles / Conseils au patient..."),
                    "class": "resize-none",
                }
            ),
            "status": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] text-sm bg-white",
                }
            ),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.vital_signs:
            vitals = self.instance.vital_signs or {}
            self.fields["tension"].initial = vitals.get("tension", "")
            self.fields["poids"].initial = vitals.get("poids", "")
            self.fields["temperature"].initial = vitals.get("temperature", "")
            self.fields["pouls"].initial = vitals.get("pouls", "")

    def save(self, commit: bool = True) -> Consultation:
        instance: Consultation = super().save(commit=False)
        instance.vital_signs = {
            "tension": self.cleaned_data.get("tension", "").strip(),
            "poids": self.cleaned_data.get("poids", "").strip(),
            "temperature": self.cleaned_data.get("temperature", "").strip(),
            "pouls": self.cleaned_data.get("pouls", "").strip(),
        }
        if commit:
            instance.save()
        return instance


class PrestationRealiseeForm(forms.ModelForm):
    """Formulaire d'ajout d'une prestation réalisée lors d'une consultation."""

    class Meta:
        model = PrestationRealisee
        fields = ["prestation", "quantity", "unit_price"]
        widgets = {
            "prestation": forms.Select(
                attrs={
                    "class": "searchable-select",
                    "data-placeholder": _("Choisir un acte / une prestation médicale..."),
                }
            ),
            "quantity": forms.NumberInput(attrs={"min": "1", "value": "1"}),
            "unit_price": forms.NumberInput(attrs={"step": "100", "placeholder": "Laissez vide pour le tarif standard"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["prestation"].queryset = Prestation.objects.filter(is_active=True).order_by("name")
        self.fields["unit_price"].required = False


class OrdonnanceForm(forms.ModelForm):
    """Formulaire d'en-tête pour la prescription d'une ordonnance."""

    class Meta:
        model = Ordonnance
        fields = ["notes"]
        widgets = {
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": _("Instructions ou conseils généraux d'administration..."),
                    "class": "resize-none",
                }
            ),
        }


class LigneOrdonnanceForm(forms.ModelForm):
    """Formulaire d'ajout d'une ligne de médicament à une ordonnance."""

    class Meta:
        model = LigneOrdonnance
        fields = ["medication_name", "posology", "duration", "quantity"]
        widgets = {
            "medication_name": forms.TextInput(attrs={"placeholder": _("Ex: Paracétamol 1g")}),
            "posology": forms.TextInput(attrs={"placeholder": _("Ex: 1 comprimé 3 fois par jour")}),
            "duration": forms.TextInput(attrs={"placeholder": _("Ex: 5 jours")}),
            "quantity": forms.NumberInput(attrs={"min": "1", "value": "1"}),
        }


class PaiementForm(forms.ModelForm):
    """Formulaire de saisie d'un paiement en caisse."""

    class Meta:
        model = Paiement
        fields = ["amount", "payment_method", "notes"]
        widgets = {
            "amount": forms.NumberInput(attrs={"step": "100", "min": "0"}),
            "payment_method": forms.Select(attrs={"class": "w-full px-4 py-2 rounded-xl border border-neutral-300 bg-white"}),
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": _("Référence transaction ou notes..."), "class": "resize-none"}),
        }

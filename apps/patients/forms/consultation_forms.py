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
    frequence_respiratoire = forms.CharField(
        label=_("Fréquence respiratoire (/min)"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "16"}),
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
        self.vital_parameters: list[dict[str, str]] = []
        if self.instance and self.instance.pk and self.instance.vital_signs:
            vitals = self.instance.vital_signs or {}
            self.fields["tension"].initial = vitals.get("tension", "")
            self.fields["poids"].initial = vitals.get("poids", "")
            self.fields["temperature"].initial = vitals.get("temperature", "")
            self.fields["pouls"].initial = vitals.get("pouls", "")
            self.fields["frequence_respiratoire"].initial = vitals.get("frequence_respiratoire", "")

            if "parameters" in vitals and isinstance(vitals["parameters"], list):
                self.vital_parameters = vitals["parameters"]
            else:
                default_defs = [
                    ("Tension artérielle", "tension", "mmHg"),
                    ("Poids", "poids", "kg"),
                    ("Température", "temperature", "°C"),
                    ("Pouls (Fréquence cardiaque)", "pouls", "bpm"),
                    ("Fréquence respiratoire", "frequence_respiratoire", "/min"),
                ]
                for name, code, unit in default_defs:
                    val = vitals.get(code, "")
                    if val:
                        self.vital_parameters.append({"name": name, "value": str(val), "unit": unit})

    def save(self, commit: bool = True) -> Consultation:
        instance: Consultation = super().save(commit=False)
        vitals: dict[str, Any] = {
            "tension": self.cleaned_data.get("tension", "").strip(),
            "poids": self.cleaned_data.get("poids", "").strip(),
            "temperature": self.cleaned_data.get("temperature", "").strip(),
            "pouls": self.cleaned_data.get("pouls", "").strip(),
            "frequence_respiratoire": self.cleaned_data.get("frequence_respiratoire", "").strip(),
        }

        # Extraire tous les paramètres personnalisés ou dynamiques définis par le personnel
        parameters: list[dict[str, str]] = []
        if self.data:
            param_names = self.data.getlist("vital_param_name[]") or self.data.getlist("vital_param_name")
            param_values = self.data.getlist("vital_param_value[]") or self.data.getlist("vital_param_value")
            param_units = self.data.getlist("vital_param_unit[]") or self.data.getlist("vital_param_unit")

            for name, val, unit in zip(param_names, param_values, param_units):
                name_clean = str(name).strip()
                val_clean = str(val).strip()
                unit_clean = str(unit).strip()
                if name_clean and val_clean:
                    parameters.append({
                        "name": name_clean,
                        "value": val_clean,
                        "unit": unit_clean,
                    })
                    # Rétrocompatibilité : synchroniser les clés standard
                    n_lower = name_clean.lower()
                    if "tension" in n_lower and not vitals["tension"]:
                        vitals["tension"] = val_clean
                    elif "poids" in n_lower and not vitals["poids"]:
                        vitals["poids"] = val_clean
                    elif "tempér" in n_lower and not vitals["temperature"]:
                        vitals["temperature"] = val_clean
                    elif ("pouls" in n_lower or "cardiaque" in n_lower) and not vitals["pouls"]:
                        vitals["pouls"] = val_clean
                    elif "respiratoire" in n_lower and not vitals["frequence_respiratoire"]:
                        vitals["frequence_respiratoire"] = val_clean

        if parameters:
            vitals["parameters"] = parameters
        else:
            default_items = []
            if vitals["tension"]:
                default_items.append({"name": "Tension artérielle", "value": vitals["tension"], "unit": "mmHg"})
            if vitals["poids"]:
                default_items.append({"name": "Poids", "value": vitals["poids"], "unit": "kg"})
            if vitals["temperature"]:
                default_items.append({"name": "Température", "value": vitals["temperature"], "unit": "°C"})
            if vitals["pouls"]:
                default_items.append({"name": "Pouls (Fréquence cardiaque)", "value": vitals["pouls"], "unit": "bpm"})
            if vitals["frequence_respiratoire"]:
                default_items.append({"name": "Fréquence respiratoire", "value": vitals["frequence_respiratoire"], "unit": "/min"})
            if default_items:
                vitals["parameters"] = default_items

        instance.vital_signs = vitals
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


class FactureUpdateForm(forms.ModelForm):
    """Formulaire de modification d'une facture non réglée."""

    class Meta:
        model = Facture
        fields = ["total_amount"]
        widgets = {
            "total_amount": forms.NumberInput(
                attrs={
                    "step": "100",
                    "min": "0",
                    "class": "w-full px-3.5 py-2.5 rounded-xl border border-neutral-300 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-[#14967F]",
                }
            ),
        }


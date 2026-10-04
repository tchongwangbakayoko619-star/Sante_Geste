"""Formulaires de gestion du module Pharmacie (Produits, Fournisseurs, Entrées de stock, Ventes)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.patients.models import Patient
from apps.pharmacy.models import Batch, Category, Product, Supplier


class CategoryForm(forms.ModelForm):
    """Formulaire d'ajout / modification d'une catégorie."""

    class Meta:
        model = Category
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": _("ex: Antibiotiques, Antipaludiques...")}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": _("Description optionnelle...")}),
        }


class SupplierForm(forms.ModelForm):
    """Formulaire de gestion d'un fournisseur pharmaceutique."""

    class Meta:
        model = Supplier
        fields = ["name", "contact_person", "telephone", "email", "address", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": _("Raison sociale du fournisseur...")}),
            "contact_person": forms.TextInput(attrs={"placeholder": _("Nom du contact commercial...")}),
            "telephone": forms.TextInput(attrs={"placeholder": _("+237 6XX XX XX XX")}),
            "email": forms.EmailInput(attrs={"placeholder": _("contact@fournisseur.com")}),
            "address": forms.Textarea(attrs={"rows": 2, "placeholder": _("Ville, quartier, adresse...")}),
        }


class ProductForm(forms.ModelForm):
    """Formulaire d'enregistrement et mise à jour d'un produit/médicament."""

    class Meta:
        model = Product
        fields = [
            "name",
            "dci",
            "dosage",
            "form",
            "reference_code",
            "unit",
            "category",
            "purchase_price",
            "selling_price",
            "min_stock_threshold",
            "is_active",
            "image",
            "description",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": _("ex: Paracétamol Biogaran, Coartem...")}),
            "dci": forms.TextInput(attrs={"placeholder": _("ex: Paracétamol, Artéméther/Luméfantrine...")}),
            "dosage": forms.TextInput(attrs={"placeholder": _("ex: 500 mg, 1 g...")}),
            "form": forms.TextInput(attrs={"placeholder": _("ex: Comprimé, Sirop, Injectable...")}),
            "reference_code": forms.TextInput(attrs={"placeholder": _("Code unique / EAN13...")}),
            "unit": forms.TextInput(attrs={"placeholder": _("Boîte, Flacon, Tube...")}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": _("Indications, posologie standard...")}),
        }

    def clean_reference_code(self) -> str:
        code = self.cleaned_data.get("reference_code", "").strip().upper()
        qs = Product.objects.filter(reference_code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("Ce code de référence est déjà utilisé par un autre produit."))
        return code


class StockEntryForm(forms.Form):
    """Formulaire de réception d'un lot fournisseur pour un produit."""

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_deleted=False).order_by("name"),
        label=_("Médicament / Produit"),
    )
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.filter(is_deleted=False, is_active=True).order_by("name"),
        required=False,
        label=_("Fournisseur"),
    )
    batch_number = forms.CharField(
        max_length=100,
        label=_("Numéro de lot"),
        widget=forms.TextInput(attrs={"placeholder": _("ex: LOT-2026-001")}),
    )
    expiry_date = forms.DateField(
        label=_("Date de péremption"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    quantity = forms.IntegerField(
        min_value=1,
        label=_("Quantité reçue"),
        widget=forms.NumberInput(attrs={"placeholder": "100"}),
    )
    purchase_price = forms.DecimalField(
        min_value=Decimal("0.00"),
        decimal_places=2,
        label=_("Prix d'achat unitaire (FCFA)"),
        widget=forms.NumberInput(attrs={"placeholder": "150"}),
    )
    selling_price = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        decimal_places=2,
        label=_("Nouveau prix de vente au public (optionnel, FCFA)"),
        widget=forms.NumberInput(attrs={"placeholder": "250"}),
    )
    notes = forms.CharField(
        required=False,
        label=_("Notes / Bordereau de livraison"),
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": _("N° BL, observations...")}),
    )

    def clean_expiry_date(self) -> date:
        exp = self.cleaned_data["expiry_date"]
        if exp <= date.today():
            raise forms.ValidationError(_("La date de péremption doit être ultérieure à la date du jour."))
        return exp


class StockAdjustmentForm(forms.Form):
    """Formulaire d'ajustement de stock pour inventaire."""

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_deleted=False).order_by("name"),
        label=_("Produit à ajuster"),
    )
    new_quantity = forms.IntegerField(
        min_value=0,
        label=_("Quantité physique réelle constatée"),
    )
    reason = forms.CharField(
        label=_("Motif de l'ajustement"),
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": _("ex: Écart d'inventaire trimestriel, comptage physique...")}),
    )

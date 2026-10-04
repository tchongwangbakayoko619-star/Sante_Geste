"""Vues de gestion du module Pharmacie (Catalogue, Stocks, Lots, Ventes, Ordonnances)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.patients.models import Ordonnance, Patient
from apps.pharmacy.forms import (
    CategoryForm,
    ProductForm,
    StockAdjustmentForm,
    StockEntryForm,
    SupplierForm,
)
from apps.pharmacy.models import Batch, Category, Product, Sale, StockMovement, Supplier
from apps.pharmacy.services import SaleService, StockService
from apps.users.mixins import (
    PharmacyAccessRequiredMixin,
    ResponsablePharmacieRequiredMixin,
    RoleRequiredMixin,
)
from utils.enums import UserRoleEnum


class PharmacyDashboardView(PharmacyAccessRequiredMixin, TemplateView):
    """Tableau de bord de la pharmacie adapté au rôle de l'utilisateur."""

    template_name = "pharmacy/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = date.today()
        warning_expiry_date = today + timedelta(days=90)  # Proche de péremption dans 90 jours

        # Indicateurs généraux
        context["total_products"] = Product.objects.filter(is_deleted=False).count()
        context["low_stock_count"] = Product.objects.filter(
            is_deleted=False, current_stock__lte=F("min_stock_threshold")
        ).count()
        context["expiring_soon_count"] = Batch.objects.filter(
            status="ACTIVE",
            current_quantity__gt=0,
            expiry_date__lte=warning_expiry_date,
            expiry_date__gt=today,
        ).count()
        context["expired_batches_count"] = Batch.objects.filter(
            status="ACTIVE",
            current_quantity__gt=0,
            expiry_date__lte=today,
        ).count()

        # Ventes du jour
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_sales = Sale.objects.filter(sale_date__gte=today_start).exclude(status="CANCELLED")
        context["today_sales_count"] = today_sales.count()
        context["today_revenue"] = today_sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")

        # Ordonnances en attente de délivrance
        context["pending_prescriptions_count"] = Ordonnance.objects.filter(status="PENDING").count()

        # Dernières ventes
        context["recent_sales"] = Sale.objects.select_related("seller", "patient").order_by("-sale_date")[:8]

        # Produits en alerte stock
        context["low_stock_products"] = Product.objects.filter(
            is_deleted=False, current_stock__lte=F("min_stock_threshold")
        ).order_by("current_stock")[:6]

        # Lots proches de la péremption
        context["expiring_batches"] = Batch.objects.filter(
            status="ACTIVE",
            current_quantity__gt=0,
            expiry_date__lte=warning_expiry_date,
        ).select_related("product", "supplier").order_by("expiry_date")[:6]

        # Valeur marchande totale estimée du stock (pour responsable)
        if user.is_responsable_pharmacie or user.is_proprietaire or user.is_superuser:
            stock_val = Product.objects.filter(is_deleted=False).aggregate(
                val=Sum(F("current_stock") * F("purchase_price"))
            )["val"]
            context["stock_total_value"] = stock_val or Decimal("0.00")

        return context


# ==============================================================================
# CATALOGUE & PRODUITS
# ==============================================================================

class ProductListView(PharmacyAccessRequiredMixin, ListView):
    """Catalogue et consultation de l'état du stock de tous les produits."""

    model = Product
    template_name = "pharmacy/product_list.html"
    context_object_name = "products"
    paginate_by = 20

    def get_queryset(self):
        qs = Product.objects.filter(is_deleted=False).select_related("category")
        q = self.request.GET.get("q", "").strip()
        cat_id = self.request.GET.get("category", "").strip()
        stock_filter = self.request.GET.get("stock", "").strip()

        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(dci__icontains=q)
                | Q(reference_code__icontains=q)
                | Q(category__name__icontains=q)
            )
        if cat_id:
            qs = qs.filter(category_id=cat_id)
        if stock_filter == "low":
            qs = qs.filter(current_stock__lte=F("min_stock_threshold"))
        elif stock_filter == "out":
            qs = qs.filter(current_stock__lte=0)
        elif stock_filter == "in_stock":
            qs = qs.filter(current_stock__gt=0)

        return qs.order_by("name")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.filter(is_deleted=False).order_by("name")
        context["q"] = self.request.GET.get("q", "")
        context["selected_category"] = self.request.GET.get("category", "")
        context["selected_stock"] = self.request.GET.get("stock", "")
        return context


class ProductDetailView(PharmacyAccessRequiredMixin, DetailView):
    """Fiche détaillée d'un médicament, état des lots actifs et historique des mouvements."""

    model = Product
    template_name = "pharmacy/product_detail.html"
    context_object_name = "product"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        context["batches"] = product.batches.select_related("supplier").order_by("expiry_date")
        context["recent_movements"] = product.stock_movements.select_related("user", "batch").order_by("-movement_date")[:10]
        context["fefo_batches"] = StockService.get_available_batches_fefo(product)
        return context


class ProductCreateView(ResponsablePharmacieRequiredMixin, CreateView):
    """Création d'un nouveau produit par le Responsable Pharmacie."""

    model = Product
    form_class = ProductForm
    template_name = "pharmacy/product_form.html"
    success_url = reverse_lazy("pharmacy:product_list")

    def form_valid(self, form):
        product = form.save(commit=False)
        product.created_by = self.request.user
        product.save()
        messages.success(self.request, _("Le médicament '%(name)s' a été enregistré avec succès.") % {"name": product.name})
        return redirect("pharmacy:product_detail", pk=product.pk)


class ProductUpdateView(ResponsablePharmacieRequiredMixin, UpdateView):
    """Modification d'un produit par le Responsable Pharmacie."""

    model = Product
    form_class = ProductForm
    template_name = "pharmacy/product_form.html"

    def form_valid(self, form):
        product = form.save(commit=False)
        product.updated_by = self.request.user
        product.save()
        messages.success(self.request, _("Les informations du produit '%(name)s' ont été mises à jour.") % {"name": product.name})
        return redirect("pharmacy:product_detail", pk=product.pk)


# ==============================================================================
# ENTRÉES & AJUSTEMENTS DE STOCK
# ==============================================================================

class StockEntryView(ResponsablePharmacieRequiredMixin, View):
    """Enregistrement d'une réception fournisseur de lots."""

    def get(self, request):
        product_id = request.GET.get("product")
        initial = {}
        if product_id:
            try:
                prod = Product.objects.get(pk=product_id)
                initial["product"] = prod
                initial["purchase_price"] = prod.purchase_price
                initial["selling_price"] = prod.selling_price
            except Product.DoesNotExist:
                pass
        form = StockEntryForm(initial=initial)
        return render(request, "pharmacy/stock_entry.html", {"form": form})

    def post(self, request):
        form = StockEntryForm(request.POST)
        if form.is_valid():
            try:
                batch = StockService.receive_batch(
                    product=form.cleaned_data["product"],
                    batch_number=form.cleaned_data["batch_number"],
                    expiry_date=form.cleaned_data["expiry_date"],
                    quantity=form.cleaned_data["quantity"],
                    purchase_price=form.cleaned_data["purchase_price"],
                    user=request.user,
                    supplier=form.cleaned_data["supplier"],
                    selling_price=form.cleaned_data["selling_price"],
                    notes=form.cleaned_data["notes"],
                )
                messages.success(
                    request,
                    _("Réception réussie : %(qty)d unités ajoutées au lot %(lot)s (%(prod)s).")
                    % {"qty": batch.initial_quantity, "lot": batch.batch_number, "prod": batch.product.name},
                )
                return redirect("pharmacy:product_detail", pk=batch.product.pk)
            except ValidationError as e:
                form.add_error(None, e.message if hasattr(e, "message") else str(e))
        return render(request, "pharmacy/stock_entry.html", {"form": form})


class StockAdjustmentView(ResponsablePharmacieRequiredMixin, View):
    """Ajustement d'inventaire d'un produit."""

    def get(self, request):
        product_id = request.GET.get("product")
        initial = {}
        if product_id:
            try:
                prod = Product.objects.get(pk=product_id)
                initial["product"] = prod
                initial["new_quantity"] = prod.current_stock
            except Product.DoesNotExist:
                pass
        form = StockAdjustmentForm(initial=initial)
        return render(request, "pharmacy/stock_adjustment.html", {"form": form})

    def post(self, request):
        form = StockAdjustmentForm(request.POST)
        if form.is_valid():
            try:
                movement = StockService.adjust_stock(
                    product=form.cleaned_data["product"],
                    new_quantity=form.cleaned_data["new_quantity"],
                    user=request.user,
                    reason=form.cleaned_data["reason"],
                )
                messages.success(
                    request,
                    _("Inventaire validé : le stock de '%(prod)s' est désormais de %(qty)d unités.")
                    % {"prod": movement.product.name, "qty": movement.new_stock},
                )
                return redirect("pharmacy:product_detail", pk=movement.product.pk)
            except ValidationError as e:
                form.add_error(None, e.message if hasattr(e, "message") else str(e))
        return render(request, "pharmacy/stock_adjustment.html", {"form": form})


class StockMovementListView(ResponsablePharmacieRequiredMixin, ListView):
    """Journal complet et inaltérable des mouvements de stock."""

    model = StockMovement
    template_name = "pharmacy/movement_list.html"
    context_object_name = "movements"
    paginate_by = 25

    def get_queryset(self):
        qs = StockMovement.objects.select_related("product", "batch", "user")
        mov_type = self.request.GET.get("type", "").strip()
        q = self.request.GET.get("q", "").strip()
        if mov_type:
            qs = qs.filter(movement_type=mov_type)
        if q:
            qs = qs.filter(
                Q(product__name__icontains=q)
                | Q(product__reference_code__icontains=q)
                | Q(reference_number__icontains=q)
            )
        return qs.order_by("-movement_date", "-created_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["movement_types"] = StockMovement.MOVEMENT_TYPES
        context["selected_type"] = self.request.GET.get("type", "")
        context["q"] = self.request.GET.get("q", "")
        return context


# ==============================================================================
# VENTES & DÉLIVRANCE
# ==============================================================================

class SaleCreateView(PharmacyAccessRequiredMixin, View):
    """Comptoir de vente pharmacie : recherche de médicaments, panier et déstockage FEFO."""

    def get(self, request):
        ordonnance_id = request.GET.get("ordonnance")
        patient_id = request.GET.get("patient")
        ordonnance = None
        patient = None
        preloaded_items = []

        if ordonnance_id:
            ordonnance = get_object_or_404(Ordonnance.objects.select_related("patient", "doctor").prefetch_related("lines"), pk=ordonnance_id)
            patient = ordonnance.patient
            # Pré-remplir les correspondances de médicaments du stock
            for line in ordonnance.lines.all():
                matching_prod = Product.objects.filter(
                    is_deleted=False,
                    name__icontains=line.medication_name,
                ).first()
                if not matching_prod:
                    matching_prod = Product.objects.filter(
                        is_deleted=False,
                        dci__icontains=line.medication_name,
                    ).first()
                preloaded_items.append({
                    "line": line,
                    "matched_product": matching_prod,
                })
        elif patient_id:
            patient = get_object_or_404(Patient, pk=patient_id)

        available_products = Product.objects.filter(is_deleted=False, is_active=True).order_by("name")
        return render(
            request,
            "pharmacy/sale_form.html",
            {
                "ordonnance": ordonnance,
                "patient": patient,
                "preloaded_items": preloaded_items,
                "available_products": available_products,
            },
        )

    def post(self, request):
        ordonnance_id = request.POST.get("ordonnance_id")
        patient_id = request.POST.get("patient_id")
        client_name = request.POST.get("client_name", "").strip()
        discount_amount = Decimal(request.POST.get("discount_amount") or "0.00")
        notes = request.POST.get("notes", "").strip()

        ordonnance = None
        if ordonnance_id:
            ordonnance = get_object_or_404(Ordonnance, pk=ordonnance_id)

        patient = None
        if patient_id:
            patient = get_object_or_404(Patient, pk=patient_id)
        elif ordonnance:
            patient = ordonnance.patient

        # Extraire les lignes du panier depuis la requête POST
        product_ids = request.POST.getlist("product_id[]")
        quantities = request.POST.getlist("quantity[]")

        if not product_ids:
            messages.error(request, _("Veuillez sélectionner au moins un médicament à délivrer."))
            return redirect(request.path)

        items_data = []
        for p_id, qty_str in zip(product_ids, quantities):
            if not p_id or not qty_str:
                continue
            try:
                prod = Product.objects.get(pk=p_id, is_deleted=False)
                qty = int(qty_str)
                if qty > 0:
                    items_data.append({"product": prod, "quantity": qty})
            except (Product.DoesNotExist, ValueError):
                continue

        if not items_data:
            messages.error(request, _("Aucun produit valide dans le panier."))
            return redirect(request.path)

        try:
            sale = SaleService.create_sale(
                seller=request.user,
                items_data=items_data,
                patient=patient,
                client_name=client_name,
                ordonnance=ordonnance,
                discount_amount=discount_amount,
                notes=notes,
            )
            messages.success(
                request,
                _("Vente %(num)s enregistrée avec succès (Total : %(total)s FCFA). La facture a été transmise à la Caisse.")
                % {"num": sale.sale_number, "total": sale.total_amount},
            )
            return redirect("pharmacy:sale_detail", pk=sale.pk)
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
            return redirect(request.path)


class SaleDetailView(PharmacyAccessRequiredMixin, DetailView):
    """Détail d'une vente pharmacie, lignes de produits, lots utilisés et reçu de délivrance."""

    model = Sale
    template_name = "pharmacy/sale_detail.html"
    context_object_name = "sale"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        sale = self.get_object()
        context["items"] = sale.items.select_related("product", "batch").all()
        return context


class SaleListView(PharmacyAccessRequiredMixin, ListView):
    """Historique des ventes de la pharmacie."""

    model = Sale
    template_name = "pharmacy/sale_list.html"
    context_object_name = "sales"
    paginate_by = 20

    def get_queryset(self):
        qs = Sale.objects.select_related("seller", "patient", "facture")
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()

        # Si simple vendeur : peut restreindre ou filtrer ses propres ventes
        if self.request.GET.get("my_sales") == "1":
            qs = qs.filter(seller=self.request.user)

        if q:
            qs = qs.filter(
                Q(sale_number__icontains=q)
                | Q(patient__last_name__icontains=q)
                | Q(patient__first_name__icontains=q)
                | Q(client_name__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)

        return qs.order_by("-sale_date")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["status_choices"] = Sale.STATUS_CHOICES
        context["selected_status"] = self.request.GET.get("status", "")
        context["q"] = self.request.GET.get("q", "")
        context["my_sales"] = self.request.GET.get("my_sales", "")
        return context


class SaleCancelView(ResponsablePharmacieRequiredMixin, View):
    """Annulation d'une vente non réglée et réintégration du stock (Responsable uniquement)."""

    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk)
        reason = request.POST.get("reason", "").strip()
        try:
            SaleService.cancel_sale(sale=sale, user=request.user, reason=reason)
            messages.success(request, _("La vente %(num)s a été annulée et le stock a été réintégré.") % {"num": sale.sale_number})
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
        return redirect("pharmacy:sale_detail", pk=sale.pk)


# ==============================================================================
# GESTION DES FOURNISSEURS & CATÉGORIES
# ==============================================================================

class SupplierListView(ResponsablePharmacieRequiredMixin, ListView):
    """Liste des fournisseurs pharmaceutiques."""

    model = Supplier
    template_name = "pharmacy/supplier_list.html"
    context_object_name = "suppliers"

    def get_queryset(self):
        return Supplier.objects.filter(is_deleted=False).order_by("name")


class SupplierCreateView(ResponsablePharmacieRequiredMixin, CreateView):
    """Ajout d'un fournisseur."""

    model = Supplier
    form_class = SupplierForm
    template_name = "pharmacy/supplier_form.html"
    success_url = reverse_lazy("pharmacy:supplier_list")

    def form_valid(self, form):
        supplier = form.save(commit=False)
        supplier.created_by = self.request.user
        supplier.save()
        messages.success(self.request, _("Fournisseur '%(name)s' ajouté avec succès.") % {"name": supplier.name})
        return redirect(self.success_url)


class CategoryListView(ResponsablePharmacieRequiredMixin, ListView):
    """Gestion des catégories pharmaceutiques."""

    model = Category
    template_name = "pharmacy/category_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return Category.objects.filter(is_deleted=False).order_by("name")


class CategoryCreateView(ResponsablePharmacieRequiredMixin, CreateView):
    """Ajout d'une catégorie."""

    model = Category
    form_class = CategoryForm
    template_name = "pharmacy/category_form.html"
    success_url = reverse_lazy("pharmacy:category_list")

    def form_valid(self, form):
        cat = form.save(commit=False)
        cat.created_by = self.request.user
        cat.save()
        messages.success(self.request, _("Catégorie '%(name)s' créée.") % {"name": cat.name})
        return redirect(self.success_url)


class BatchListView(ResponsablePharmacieRequiredMixin, ListView):
    """Suivi exhaustif de tous les lots en stock, alertes péremption et tri FEFO."""

    model = Batch
    template_name = "pharmacy/batch_list.html"
    context_object_name = "batches"
    paginate_by = 25

    def get_queryset(self):
        qs = Batch.objects.select_related("product", "supplier")
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()

        if q:
            qs = qs.filter(
                Q(batch_number__icontains=q)
                | Q(product__name__icontains=q)
                | Q(product__reference_code__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)

        return qs.order_by("expiry_date", "entry_date")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["status_choices"] = Batch.STATUS_CHOICES
        context["selected_status"] = self.request.GET.get("status", "")
        context["q"] = self.request.GET.get("q", "")
        return context


class PharmacyReportView(ResponsablePharmacieRequiredMixin, TemplateView):
    """Rapports d'activité, ventes et valeur des stocks de la pharmacie."""

    template_name = "pharmacy/reports.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        today = date.today()
        month_start = today.replace(day=1)

        # Chiffre d'affaires global et du mois
        month_sales = Sale.objects.filter(sale_date__gte=month_start).exclude(status="CANCELLED")
        context["month_revenue"] = month_sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        context["month_sales_count"] = month_sales.count()

        # Top 5 médicaments les plus vendus
        from django.db.models import Count
        context["top_products"] = (
            Product.objects.filter(sale_items__sale__status="COMPLETED")
            .annotate(total_sold=Sum("sale_items__quantity"))
            .order_by("-total_sold")[:5]
        )

        # Valeur totale du stock
        context["stock_val"] = Product.objects.filter(is_deleted=False).aggregate(
            val=Sum(F("current_stock") * F("purchase_price"))
        )["val"] or Decimal("0.00")

        return context


class PharmacySettingsView(ResponsablePharmacieRequiredMixin, TemplateView):
    """Paramètres et configuration du module Pharmacie (seuils, catégories, fournisseurs)."""

    template_name = "pharmacy/settings.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["categories_count"] = Category.objects.filter(is_deleted=False).count()
        context["suppliers_count"] = Supplier.objects.filter(is_deleted=False).count()
        context["products_count"] = Product.objects.filter(is_deleted=False).count()
        return context


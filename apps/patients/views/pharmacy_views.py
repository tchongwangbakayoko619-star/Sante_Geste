"""Vues de délivrance des ordonnances et gestion pharmacie pour SantéGeste."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import ListView

from apps.patients.models import Ordonnance
from apps.users.mixins import RoleRequiredMixin
from utils.enums import UserRoleEnum


class PharmacyOrdonnanceListView(RoleRequiredMixin, ListView):
    """Liste de toutes les ordonnances médicales transmises à la pharmacie."""

    model = Ordonnance
    template_name = "patients/pharmacy_ordonnance_list.html"
    context_object_name = "ordonnances"
    paginate_by = 20

    required_roles = [
        UserRoleEnum.RESPONSABLE_PHARMACIE,
        UserRoleEnum.VENDEUR_PHARMACIE,
        UserRoleEnum.PROPRIETAIRE,
    ]
    require_all_roles = False

    def get_queryset(self) -> QuerySet[Ordonnance]:
        qs = Ordonnance.objects.select_related("patient", "doctor", "delivered_by").prefetch_related("lines")
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "PENDING").strip()

        if query:
            qs = qs.filter(
                models.Q(patient__last_name__icontains=query)
                | models.Q(patient__first_name__icontains=query)
                | models.Q(patient__patient_number__icontains=query)
                | models.Q(doctor__last_name__icontains=query)
                | models.Q(lines__medication_name__icontains=query)
            ).distinct()

        if status and status != "ALL":
            qs = qs.filter(status=status)

        return qs.order_by("-prescribed_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["selected_status"] = self.request.GET.get("status", "PENDING").strip()
        context["status_choices"] = Ordonnance._meta.get_field("status").choices
        return context


from apps.pharmacy.models import Batch, Product, StockMovement
from apps.pharmacy.services.stock_service import StockService


class PharmacyOrdonnanceDispenseView(RoleRequiredMixin, View):
    """Validation et délivrance effective d'une ordonnance à la pharmacie ou en consultation.

    Effectue le déstockage des médicaments prescrits selon la stratégie FEFO.
    """

    required_roles = [
        UserRoleEnum.PERSONNEL_MEDICAL,
        UserRoleEnum.RESPONSABLE_PHARMACIE,
        UserRoleEnum.VENDEUR_PHARMACIE,
        UserRoleEnum.PROPRIETAIRE,
    ]
    require_all_roles = False

    def post(self, request: Any, pk: Any):
        ordonnance = get_object_or_404(Ordonnance.objects.prefetch_related("lines"), pk=pk)
        next_url = request.POST.get("next") or request.GET.get("next")
        
        if ordonnance.status == "DELIVERED":
            messages.info(request, _("Cette ordonnance a déjà été délivrée."))
            if next_url:
                return redirect(next_url)
            return redirect("patients:pharmacy_ordonnance_list")

        # Déstockage automatique des médicaments correspondants dans le catalogue pharmacie
        destocked_summary = []
        for line in ordonnance.lines.all():
            matching_prod = Product.objects.filter(
                is_deleted=False, is_active=True, name__iexact=line.medication_name
            ).first()
            if not matching_prod:
                matching_prod = Product.objects.filter(
                    is_deleted=False, is_active=True, name__icontains=line.medication_name
                ).first()

            if matching_prod and matching_prod.current_stock >= line.quantity:
                try:
                    allocations = StockService.allocate_stock_fefo(matching_prod, line.quantity)
                    for alloc in allocations:
                        batch = alloc["batch"]
                        qty_allocated = alloc["quantity"]

                        batch.current_quantity -= qty_allocated
                        if batch.current_quantity == 0:
                            batch.status = "DEPLETED"
                        batch.save(update_fields=["current_quantity", "status", "updated_at"])

                        prev_stock = matching_prod.current_stock
                        matching_prod.current_stock -= qty_allocated
                        matching_prod.save(update_fields=["current_stock", "updated_at"])

                        StockMovement.objects.create(
                            product=matching_prod,
                            batch=batch,
                            movement_type="OUT_DISPENSE",
                            quantity=-qty_allocated,
                            previous_stock=prev_stock,
                            new_stock=matching_prod.current_stock,
                            user=request.user,
                            reference_number=f"ORD-{ordonnance.pk.hex[:8].upper()}",
                            reason=f"Délivrance ordonnance pour {ordonnance.patient.full_name}",
                            created_by=request.user,
                        )
                    destocked_summary.append(f"{line.medication_name} ({line.quantity})")
                except Exception:
                    pass

        ordonnance.status = "DELIVERED"
        ordonnance.delivered_at = timezone.now()
        ordonnance.delivered_by = request.user
        ordonnance.save(update_fields=["status", "delivered_at", "delivered_by", "updated_at"])

        if destocked_summary:
            messages.success(
                request,
                _("L'ordonnance du patient %(patient)s a été délivrée. Stock décrémenté pour : %(items)s.")
                % {"patient": ordonnance.patient.full_name, "items": ", ".join(destocked_summary)},
            )
        else:
            messages.success(
                request,
                _("L'ordonnance du patient %(patient)s a été marquée comme délivrée par %(user)s.")
                % {"patient": ordonnance.patient.full_name, "user": request.user.full_name},
            )
        if next_url:
            return redirect(next_url)
        return redirect("patients:pharmacy_ordonnance_list")

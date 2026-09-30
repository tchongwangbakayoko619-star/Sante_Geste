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


class PharmacyOrdonnanceDispenseView(RoleRequiredMixin, View):
    """Validation et délivrance effective d'une ordonnance à la pharmacie."""

    required_roles = [
        UserRoleEnum.RESPONSABLE_PHARMACIE,
        UserRoleEnum.VENDEUR_PHARMACIE,
        UserRoleEnum.PROPRIETAIRE,
    ]
    require_all_roles = False

    def post(self, request: Any, pk: Any):
        ordonnance = get_object_or_404(Ordonnance, pk=pk)
        
        if ordonnance.status == "DELIVERED":
            messages.info(request, _("Cette ordonnance a déjà été délivrée."))
            return redirect("patients:pharmacy_ordonnance_list")

        ordonnance.status = "DELIVERED"
        ordonnance.delivered_at = timezone.now()
        ordonnance.delivered_by = request.user
        ordonnance.save(update_fields=["status", "delivered_at", "delivered_by", "updated_at"])

        messages.success(
            request,
            _("L'ordonnance du patient %(patient)s a été marquée comme délivrée à la pharmacie par %(pharmacist)s.")
            % {"patient": ordonnance.patient.full_name, "pharmacist": request.user.full_name},
        )
        return redirect("patients:pharmacy_ordonnance_list")

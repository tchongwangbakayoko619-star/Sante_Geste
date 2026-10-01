"""Vues de gestion du module Caisse, de la facturation et des règlements financiers."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.db import models
from django.db import transaction
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView
from django.views.generic import FormView
from django.views.generic import ListView

from apps.patients.forms import FactureUpdateForm
from apps.patients.forms import PaiementForm
from apps.patients.models import Facture
from apps.patients.models import Paiement
from apps.patients.models import Patient
from apps.patients.models import PrestationRealisee
from apps.users.mixins import CaissierRequiredMixin


class CaissePendingListView(CaissierRequiredMixin, ListView):
    """File d'attente des prestations réalisées en attente de facturation et d'encaissement."""

    model = PrestationRealisee
    template_name = "patients/caisse_pending_list.html"
    context_object_name = "prestations"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[PrestationRealisee]:
        qs = PrestationRealisee.objects.filter(status="EN_ATTENTE_CAISSE").select_related(
            "patient", "prestation", "doctor", "consultation"
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                models.Q(patient__last_name__icontains=query)
                | models.Q(patient__first_name__icontains=query)
                | models.Q(patient__patient_number__icontains=query)
                | models.Q(prestation__name__icontains=query)
            )
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        # Groupement par patient pour faciliter la facturation groupée
        pending = context["prestations"]
        patients_map = {}
        for item in pending:
            p_id = item.patient_id
            if p_id not in patients_map:
                patients_map[p_id] = {
                    "patient": item.patient,
                    "items": [],
                    "total": 0,
                }
            patients_map[p_id]["items"].append(item)
            patients_map[p_id]["total"] += item.total_price
        context["grouped_patients"] = list(patients_map.values())
        return context


class FactureCreateView(CaissierRequiredMixin, View):
    """Génération d'une facture de caisse pour les prestations en attente d'un patient."""

    def post(self, request: Any, patient_id: Any):
        patient = get_object_or_404(Patient, pk=patient_id)
        prestation_ids = request.POST.getlist("prestation_ids")

        with transaction.atomic():
            if prestation_ids:
                pending_items = PrestationRealisee.objects.filter(
                    id__in=prestation_ids, patient=patient, status="EN_ATTENTE_CAISSE"
                )
            else:
                pending_items = PrestationRealisee.objects.filter(
                    patient=patient, status="EN_ATTENTE_CAISSE"
                )

            if not pending_items.exists():
                messages.warning(request, _("Aucune prestation en attente de facturation trouvée pour ce patient."))
                return redirect("patients:caisse_pending_list")

            total_sum = sum(item.total_price for item in pending_items)
            invoice_num = f"FAC-{timezone.now().strftime('%Y%m%d')}-{Facture.objects.count() + 1:04d}"

            facture = Facture.objects.create(
                invoice_number=invoice_num,
                patient=patient,
                total_amount=total_sum,
                paid_amount=0,
                status="UNPAID",
                issued_by=request.user,
            )

            pending_items.update(status="FACTURE")

            messages.success(
                request,
                _("Facture N° %(num)s générée avec succès pour un montant de %(amount)s FCFA.")
                % {"num": invoice_num, "amount": f"{total_sum:,.0f}"},
            )
            return redirect("patients:facture_detail", pk=facture.pk)


class FactureDetailView(CaissierRequiredMixin, DetailView):
    """Affichage détaillé d'une facture avec reçu de paiement et formulaire d'encaissement."""

    model = Facture
    template_name = "patients/facture_detail.html"
    context_object_name = "facture"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["paiements"] = self.object.paiements.select_related("cashier")
        context["paiement_form"] = PaiementForm(initial={"amount": self.object.remaining_amount})
        return context


class PaiementCreateView(CaissierRequiredMixin, View):
    """Enregistrement d'un règlement financier perçu à la caisse."""

    def post(self, request: Any, pk: Any):
        facture = get_object_or_404(Facture, pk=pk)
        
        post_data = request.POST.copy()
        if "amount" in post_data:
            raw_amount = post_data["amount"].replace(" ", "").replace("\xa0", "").replace("FCFA", "").replace("fcfa", "").strip()
            # remplace virgule par point pour format decimal
            if "," in raw_amount and "." not in raw_amount:
                raw_amount = raw_amount.replace(",", ".")
            post_data["amount"] = raw_amount

        form = PaiementForm(post_data)

        if form.is_valid():
            amount = form.cleaned_data["amount"]
            method = form.cleaned_data["payment_method"]
            notes = form.cleaned_data.get("notes", "")

            Paiement.objects.create(
                facture=facture,
                cashier=request.user,
                amount=amount,
                payment_method=method,
                notes=notes,
            )

            messages.success(
                request,
                _("Paiement de %(amount)s FCFA enregistré par %(method)s pour la facture N° %(num)s.")
                % {
                    "amount": f"{amount:,.0f}",
                    "method": dict(Paiement._meta.get_field("payment_method").choices).get(method, method),
                    "num": facture.invoice_number,
                },
            )
        else:
            errors_summary = []
            for field, errs in form.errors.items():
                label = form.fields[field].label if field in form.fields else field
                errors_summary.append(f"{label}: {' '.join(errs)}")
            err_text = " | ".join(errors_summary) if errors_summary else _("Veuillez vérifier les informations saisies.")
            messages.error(request, _("Erreur de paiement : ") + err_text)

        return redirect("patients:facture_detail", pk=facture.pk)


class FactureListView(CaissierRequiredMixin, ListView):
    """Historique complet de toutes les factures et états d'encaissement de caisse."""

    model = Facture
    template_name = "patients/facture_list.html"
    context_object_name = "factures"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[Facture]:
        qs = Facture.objects.select_related("patient", "issued_by")
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()

        if query:
            qs = qs.filter(
                models.Q(invoice_number__icontains=query)
                | models.Q(patient__last_name__icontains=query)
                | models.Q(patient__first_name__icontains=query)
                | models.Q(patient__patient_number__icontains=query)
            )

        if status:
            qs = qs.filter(status=status)

        return qs.order_by("-issued_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["selected_status"] = self.request.GET.get("status", "").strip()
        context["status_choices"] = Facture._meta.get_field("status").choices
        return context


class FacturePrintView(CaissierRequiredMixin, DetailView):
    """Vue d'impression et d'export au format reçu officiel / PDF d'une facture de caisse."""

    model = Facture
    template_name = "patients/facture_print.html"
    context_object_name = "facture"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["paiements"] = self.object.paiements.select_related("cashier")
        if self.object.consultation:
            context["prestations"] = self.object.consultation.prestations.select_related("prestation")
        return context


class FactureUpdateView(CaissierRequiredMixin, View):
    """Modification du montant d'une facture non encore payée."""

    def post(self, request: Any, pk: Any):
        facture = get_object_or_404(Facture, pk=pk)

        # Règle comptable : interdiction de modifier une facture déjà réglée
        if facture.status == "PAID" or facture.paid_amount > 0:
            messages.error(
                request,
                _("Impossible de modifier une facture ayant déjà fait l'objet d'un encaissement."),
            )
            return redirect("patients:facture_detail", pk=facture.pk)

        if facture.status == "CANCELLED":
            messages.error(request, _("Impossible de modifier une facture annulée."))
            return redirect("patients:facture_detail", pk=facture.pk)

        form = FactureUpdateForm(request.POST, instance=facture)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                _("Le montant de la facture N° %(num)s a été ajusté avec succès.")
                % {"num": facture.invoice_number},
            )
        else:
            messages.error(request, _("Veuillez saisir un montant valide."))

        return redirect("patients:facture_detail", pk=facture.pk)


class FactureCancelView(CaissierRequiredMixin, View):
    """Annulation d'une facture de caisse et réouverture des prestations."""

    def post(self, request: Any, pk: Any):
        facture = get_object_or_404(Facture, pk=pk)

        if facture.status == "PAID" or facture.paid_amount > 0:
            messages.error(
                request,
                _("Impossible d'annuler une facture déjà payée ou partiellement réglée."),
            )
            return redirect("patients:facture_detail", pk=facture.pk)

        if facture.status == "CANCELLED":
            messages.warning(request, _("Cette facture est déjà annulée."))
            return redirect("patients:facture_detail", pk=facture.pk)

        with transaction.atomic():
            facture.status = "CANCELLED"
            facture.save(update_fields=["status", "updated_at"])

            # Si liée à une consultation, remettre les prestations au statut EN_ATTENTE_CAISSE
            if facture.consultation:
                facture.consultation.prestations.filter(status="FACTURE").update(
                    status="EN_ATTENTE_CAISSE"
                )

        messages.success(
            request,
            _("La facture N° %(num)s a été annulée. Les actes associés sont à nouveau disponibles pour facturation.")
            % {"num": facture.invoice_number},
        )
        return redirect("patients:facture_detail", pk=facture.pk)



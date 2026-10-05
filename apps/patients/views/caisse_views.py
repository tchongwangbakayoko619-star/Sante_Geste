"""Vues de gestion du module Caisse, de la facturation et des règlements financiers."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import models
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView
from django.views.generic import ListView

from apps.patients.forms import FactureUpdateForm
from apps.patients.forms import PaiementForm
from apps.patients.models import Facture
from apps.patients.models import Paiement
from apps.patients.models import Patient
from apps.patients.models import PrestationRealisee
from apps.patients.services import PaymentService
from apps.users.mixins import CaissierRequiredMixin
from apps.users.mixins import ProprietaireRequiredMixin

if TYPE_CHECKING:
    from django.db.models import QuerySet


class CaissePendingListView(CaissierRequiredMixin, ListView):
    """File d'attente des prestations en attente de facturation et encaissement."""

    model = PrestationRealisee
    template_name = "patients/caisse_pending_list.html"
    context_object_name = "prestations"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[PrestationRealisee]:
        qs = PrestationRealisee.objects.filter(
            status="EN_ATTENTE_CAISSE"
        ).select_related("patient", "prestation", "doctor", "consultation")
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
    """Génération d'une facture de caisse pour les prestations d'un patient."""

    def post(self, request: Any, patient_id: Any):
        patient = get_object_or_404(Patient, pk=patient_id)
        prestation_ids = request.POST.getlist("prestation_ids")

        if prestation_ids:
            pending_items = list(
                PrestationRealisee.objects.filter(
                    id__in=prestation_ids,
                    patient=patient,
                    status="EN_ATTENTE_CAISSE",
                )
            )
        else:
            pending_items = list(
                PrestationRealisee.objects.filter(
                    patient=patient,
                    status="EN_ATTENTE_CAISSE",
                )
            )

        if not pending_items:
            messages.warning(
                request,
                _(
                    "Aucune prestation en attente de facturation "
                    "trouvée pour ce patient."
                ),
            )
            return redirect("patients:caisse_pending_list")

        try:
            facture = PaymentService.create_invoice(
                patient=patient,
                prestations=pending_items,
                cashier=request.user,
            )
            messages.success(
                request,
                _(
                    "Facture N° %(num)s générée pour %(amount)s FCFA. "
                    "Statut : NON PAYÉE."
                )
                % {
                    "num": facture.invoice_number,
                    "amount": f"{facture.total_amount:,.0f}",
                },
            )
            return redirect("patients:facture_detail", pk=facture.pk)
        except ValidationError as e:
            err_msg = e.message if hasattr(e, "message") else " ".join(e.messages)
            messages.error(
                request,
                _("Erreur lors de la facturation : ") + str(err_msg),
            )
            return redirect("patients:caisse_pending_list")


class FactureDetailView(CaissierRequiredMixin, DetailView):
    """Affichage détaillé d'une facture avec prestations et règlements."""

    model = Facture
    template_name = "patients/facture_detail.html"
    context_object_name = "facture"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        facture = self.object
        context["paiements"] = facture.paiements.select_related(
            "cashier"
        ).order_by("-paid_at")

        prestations = list(
            facture.prestations_realisees.select_related("prestation", "doctor")
        )
        if not prestations and facture.consultation:
            prestations = list(
                facture.consultation.prestations.select_related(
                    "prestation", "doctor"
                )
            )
        context["prestations"] = prestations
        context["paiement_form"] = PaiementForm(
            initial={"amount": facture.remaining_amount}
        )
        return context


class PaiementCreateView(CaissierRequiredMixin, View):
    """Enregistrement et confirmation explicite d'un règlement financier."""

    def post(self, request: Any, pk: Any):
        facture = get_object_or_404(Facture, pk=pk)

        post_data = request.POST.copy()
        if "amount" in post_data:
            raw_amount = (
                post_data["amount"]
                .replace(" ", "")
                .replace("\xa0", "")
                .replace("FCFA", "")
                .replace("fcfa", "")
                .strip()
            )
            if "," in raw_amount and "." not in raw_amount:
                raw_amount = raw_amount.replace(",", ".")
            post_data["amount"] = raw_amount

        form = PaiementForm(post_data)

        if form.is_valid():
            amount = form.cleaned_data["amount"]
            method = form.cleaned_data["payment_method"]
            notes = form.cleaned_data.get("notes", "")

            try:
                paiement = PaymentService.confirm_payment(
                    facture=facture,
                    amount=amount,
                    payment_method=method,
                    cashier=request.user,
                    notes=notes,
                )

                method_label = dict(Paiement.PAYMENT_METHOD_CHOICES).get(
                    method, method
                )
                messages.success(
                    request,
                    _(
                        "Paiement de %(amount)s FCFA par %(method)s enregistré "
                        "pour la facture N° %(num)s. Reçu N° %(rec)s émis."
                    )
                    % {
                        "amount": f"{amount:,.0f}",
                        "method": method_label,
                        "num": facture.invoice_number,
                        "rec": paiement.receipt_number,
                    },
                )
                return redirect("patients:paiement_receipt", pk=paiement.pk)
            except ValidationError as e:
                err_msg = e.message if hasattr(e, "message") else " ".join(e.messages)
                messages.error(request, _("Erreur d'encaissement : ") + str(err_msg))
        else:
            errors_summary = []
            for field, errs in form.errors.items():
                label = form.fields[field].label if field in form.fields else field
                errors_summary.append(f"{label}: {' '.join(errs)}")
            err_text = (
                " | ".join(errors_summary)
                if errors_summary
                else _("Veuillez vérifier les informations saisies.")
            )
            messages.error(request, _("Erreur de paiement : ") + err_text)

        return redirect("patients:facture_detail", pk=facture.pk)


class PaiementReceiptView(CaissierRequiredMixin, DetailView):
    """Affichage et impression du reçu de paiement officiel (preuve de paiement)."""

    model = Paiement
    template_name = "patients/paiement_receipt.html"
    context_object_name = "paiement"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        paiement = self.object
        context["facture"] = paiement.facture
        return context


class FactureListView(CaissierRequiredMixin, ListView):
    """Historique complet des factures avec recherche, filtres et statuts."""

    model = Facture
    template_name = "patients/facture_list.html"
    context_object_name = "factures"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[Facture]:
        qs = Facture.objects.select_related(
            "patient", "issued_by"
        ).prefetch_related("paiements")
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        date_filter = self.request.GET.get("date", "").strip()

        if query:
            qs = qs.filter(
                models.Q(invoice_number__icontains=query)
                | models.Q(patient__last_name__icontains=query)
                | models.Q(patient__first_name__icontains=query)
                | models.Q(patient__patient_number__icontains=query)
            )

        if status:
            qs = qs.filter(status=status)

        if date_filter:
            try:
                parsed_date = date.fromisoformat(date_filter)
                qs = qs.filter(issued_at__date=parsed_date)
            except ValueError:
                pass

        return qs.order_by("-issued_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["selected_status"] = self.request.GET.get("status", "").strip()
        context["date_filter"] = self.request.GET.get("date", "").strip()
        context["status_choices"] = Facture.STATUS_CHOICES

        all_qs = Facture.objects.all()
        context["count_total"] = all_qs.count()
        context["count_unpaid"] = all_qs.filter(status="UNPAID").count()
        context["count_partially_paid"] = all_qs.filter(
            status="PARTIALLY_PAID"
        ).count()
        context["count_paid"] = all_qs.filter(status="PAID").count()
        context["count_cancelled"] = all_qs.filter(status="CANCELLED").count()
        return context


class FacturePrintView(CaissierRequiredMixin, DetailView):
    """Vue d'impression et d'export au format officiel d'une facture de caisse."""

    model = Facture
    template_name = "patients/facture_print.html"
    context_object_name = "facture"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["paiements"] = self.object.paiements.select_related(
            "cashier"
        ).order_by("paid_at")
        prestations = list(
            self.object.prestations_realisees.select_related("prestation", "doctor")
        )
        if not prestations and self.object.consultation:
            prestations = list(
                self.object.consultation.prestations.select_related(
                    "prestation", "doctor"
                )
            )
        context["prestations"] = prestations
        return context


class FactureUpdateView(ProprietaireRequiredMixin, View):
    """Modification du montant d'une facture non réglée (Propriétaire uniquement)."""

    def post(self, request: Any, pk: Any):
        facture = get_object_or_404(Facture, pk=pk)

        if facture.status == "PAID" or facture.paid_amount > 0:
            messages.error(
                request,
                _(
                    "Impossible de modifier une facture ayant déjà "
                    "fait l'objet d'un encaissement."
                ),
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
                _("Le montant de la facture N° %(num)s a été ajusté.")
                % {"num": facture.invoice_number},
            )
        else:
            messages.error(request, _("Veuillez saisir un montant valide."))

        return redirect("patients:facture_detail", pk=facture.pk)


class FactureCancelView(CaissierRequiredMixin, View):
    """Annulation d'une facture de caisse et réouverture des prestations."""

    def post(self, request: Any, pk: Any):
        facture = get_object_or_404(Facture, pk=pk)

        try:
            PaymentService.cancel_invoice(facture=facture, user=request.user)
            messages.success(
                request,
                _(
                    "La facture N° %(num)s a été annulée. "
                    "Les actes associés sont à nouveau disponibles pour facturation."
                )
                % {"num": facture.invoice_number},
            )
        except ValidationError as e:
            err_msg = e.message if hasattr(e, "message") else " ".join(e.messages)
            messages.error(request, str(err_msg))

        return redirect("patients:facture_detail", pk=facture.pk)

"""Vues de gestion des consultations médicales, prestations et prescriptions."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import Any

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView
from django.views.generic import DetailView
from django.views.generic import FormView
from django.views.generic import ListView

from apps.patients.forms import ConsultationForm
from apps.patients.forms import LigneOrdonnanceForm
from apps.patients.forms import OrdonnanceForm
from apps.patients.forms import PrestationRealiseeForm
from apps.patients.models import Appointment
from apps.patients.models import Consultation
from apps.patients.models import LigneOrdonnance
from apps.patients.models import Ordonnance
from apps.patients.models import Patient
from apps.patients.models import Prestation
from apps.patients.models import PrestationRealisee
from apps.users.mixins import PatientManagementRequiredMixin
from apps.users.mixins import PersonnelMedicalRequiredMixin
from apps.users.services import rbac as rbac_service
from utils.enums import AppointmentStatusEnum

User = get_user_model()


class DoctorAppointmentListView(PersonnelMedicalRequiredMixin, ListView):
    """Vue 'Mes rendez-vous' réservée au personnel médical connecté."""

    model = Appointment
    template_name = "patients/doctor_appointment_list.html"
    context_object_name = "appointments"
    paginate_by = 50

    def get_queryset(self) -> QuerySet[Appointment]:
        # Le personnel médical ne voit QUE ses propres rendez-vous sauf s'il est superuser/propriétaire
        qs = Appointment.objects.select_related("patient", "doctor")

        if not (self.request.user.is_superuser or self.request.user.is_proprietaire):
            qs = qs.filter(doctor=self.request.user)

        # Filtre par statut
        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)

        # Filtre par date
        date_param = self.request.GET.get("date", "").strip()
        date_filter = self.request.GET.get("date_filter", "today").strip()
        now = timezone.now()

        if date_param:
            try:
                target_date = datetime.strptime(date_param, "%Y-%m-%d").date()
                day_start = timezone.make_aware(datetime.combine(target_date, datetime.min.time()))
                day_end = day_start + timedelta(days=1)
                qs = qs.filter(scheduled_at__gte=day_start, scheduled_at__lt=day_end)
            except (ValueError, TypeError):
                pass
        elif date_filter == "today":
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            today_qs = qs.filter(scheduled_at__gte=today_start, scheduled_at__lt=today_end)
            if not today_qs.exists() and qs.exists():
                # Si aucun RDV aujourd'hui mais qu'il y en a dans la base, on affiche l'ensemble pour éviter un agenda vide
                qs = qs
            else:
                qs = today_qs
        elif date_filter == "upcoming":
            qs = qs.filter(scheduled_at__gte=now)
        elif date_filter == "past":
            qs = qs.filter(scheduled_at__lt=now)

        return qs.order_by("scheduled_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        date_param = self.request.GET.get("date", "").strip()
        if date_param:
            try:
                current_date = datetime.strptime(date_param, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                current_date = now.date()
        else:
            current_date = now.date()

        context["current_date"] = current_date
        context["prev_date"] = (current_date - timedelta(days=1)).strftime("%Y-%m-%d")
        context["next_date"] = (current_date + timedelta(days=1)).strftime("%Y-%m-%d")
        context["today_date"] = now.date().strftime("%Y-%m-%d")
        context["hours"] = ["08", "09", "10", "11", "12", "13", "14", "15", "16", "17"]
        context["selected_status"] = self.request.GET.get("status", "").strip()
        context["date_filter"] = self.request.GET.get("date_filter", "today").strip()
        context["status_choices"] = AppointmentStatusEnum.choices
        return context


class ConsultationCreateView(PersonnelMedicalRequiredMixin, CreateView):
    """Démarrage et enregistrement d'une nouvelle consultation médicale."""

    model = Consultation
    form_class = ConsultationForm
    template_name = "patients/consultation_form.html"

    def dispatch(self, request: Any, *args: Any, **kwargs: Any):
        self.appointment = None
        appointment_id = request.GET.get("appointment") or request.POST.get("appointment")
        if appointment_id:
            self.appointment = get_object_or_404(Appointment, pk=appointment_id)
            # Vérification de sécurité RBAC au niveau de l'objet : un médecin ne peut pas ouvrir le RDV d'un autre
            if not (request.user.is_superuser or request.user.is_proprietaire):
                if self.appointment.doctor_id and self.appointment.doctor_id != request.user.id:
                    doc_name = self.appointment.doctor.full_name if self.appointment.doctor else _("un autre praticien")
                    messages.error(
                        request,
                        _("Ce rendez-vous est attribué au Dr. %(doctor)s. Vous êtes actuellement connecté avec le compte %(user)s et ne pouvez pas démarrer la consultation d'un autre praticien.")
                        % {"doctor": doc_name, "user": request.user.full_name},
                    )
                    return redirect("patients:my_appointments")

        self.patient = None
        patient_id = request.GET.get("patient") or request.POST.get("patient")
        if patient_id:
            self.patient = get_object_or_404(Patient, pk=patient_id)
        elif self.appointment:
            self.patient = self.appointment.patient

        if not self.patient:
            messages.error(request, _("Veuillez sélectionner un patient valide pour démarrer une consultation."))
            return redirect("patients:appointment_list")

        return super().dispatch(request, *args, **kwargs)

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        if self.appointment:
            initial["reason"] = self.appointment.reason
        return initial

    def form_valid(self, form: ConsultationForm):
        consultation = form.save(commit=False)
        consultation.patient = self.patient
        consultation.doctor = self.request.user
        if self.appointment:
            consultation.appointment = self.appointment
            self.appointment.status = AppointmentStatusEnum.COMPLETED
            if not self.appointment.doctor_id:
                self.appointment.doctor = self.request.user
                self.appointment.save(update_fields=["status", "doctor", "updated_at"])
            else:
                self.appointment.save(update_fields=["status", "updated_at"])
        consultation.save()

        # Si aucune prestation n'est encore saisie, ajouter par défaut la prestation "Consultation Générale" s'il existe une prestation standard
        default_prestation = Prestation.objects.filter(is_active=True).first()
        if default_prestation:
            PrestationRealisee.objects.create(
                patient=self.patient,
                consultation=consultation,
                prestation=default_prestation,
                doctor=self.request.user,
                quantity=1,
                unit_price=default_prestation.standard_price,
                status="EN_ATTENTE_CAISSE",
            )

        messages.success(
            self.request,
            _("La consultation médicale pour le patient %(patient)s a été enregistrée avec succès.")
            % {"patient": self.patient.full_name},
        )
        return redirect("patients:consultation_detail", pk=consultation.pk)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["patient"] = self.patient
        context["appointment"] = self.appointment
        return context


class ConsultationDetailView(PatientManagementRequiredMixin, DetailView):
    """Détail clinique d'une consultation (motif, constantes, diagnostic, prestations, ordonnances)."""

    model = Consultation
    template_name = "patients/consultation_detail.html"
    context_object_name = "consultation"

    def dispatch(self, request: Any, *args: Any, **kwargs: Any):
        consultation = self.get_object()
        # Contrôle RBAC objet : restriction au médecin traitant sauf superuser/propriétaire ou consultation partagée
        if request.user.is_personnel_medical and not (request.user.is_superuser or request.user.is_proprietaire or request.user.is_agent_accueil):
            if consultation.doctor_id != request.user.id:
                raise PermissionDenied(_("Accès non autorisé à la consultation d'un autre praticien."))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["patient"] = self.object.patient
        context["prestations"] = self.object.prestations.select_related("prestation")
        context["ordonnances"] = self.object.ordonnances.prefetch_related("lines")
        context["prestation_form"] = PrestationRealiseeForm()
        context["ordonnance_form"] = OrdonnanceForm()
        context["ligne_form"] = LigneOrdonnanceForm()
        context["can_prescribe"] = rbac_service.can_prescribe(self.request.user)
        return context


class ConsultationListView(PatientManagementRequiredMixin, ListView):
    """Liste de toutes les consultations enregistrées avec filtres sémantiques."""

    model = Consultation
    template_name = "patients/consultation_list.html"
    context_object_name = "consultations"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[Consultation]:
        qs = Consultation.objects.select_related("patient", "doctor")

        # Filtrage par médecin si praticien unique
        if self.request.user.is_personnel_medical and not (self.request.user.is_superuser or self.request.user.is_proprietaire or self.request.user.is_agent_accueil):
            qs = qs.filter(doctor=self.request.user)

        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                models.Q(patient__last_name__icontains=query)
                | models.Q(patient__first_name__icontains=query)
                | models.Q(patient__patient_number__icontains=query)
                | models.Q(diagnosis__icontains=query)
                | models.Q(reason__icontains=query)
            )

        return qs.order_by("-consultation_date")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        return context


class PrestationRealiseeCreateView(PersonnelMedicalRequiredMixin, View):
    """Enregistrement d'une prestation médicale réalisée durant une consultation."""

    def post(self, request: Any, pk: Any):
        consultation = get_object_or_404(Consultation, pk=pk)
        form = PrestationRealiseeForm(request.POST)

        if form.is_valid():
            prestation_item = form.cleaned_data["prestation"]
            quantity = form.cleaned_data.get("quantity") or 1
            unit_price = form.cleaned_data.get("unit_price") or prestation_item.standard_price

            PrestationRealisee.objects.create(
                patient=consultation.patient,
                consultation=consultation,
                prestation=prestation_item,
                doctor=request.user,
                quantity=quantity,
                unit_price=unit_price,
                status="EN_ATTENTE_CAISSE",
            )
            messages.success(
                request,
                _("La prestation « %(name)s » a été ajoutée et transmise à la caisse.")
                % {"name": prestation_item.name},
            )
        else:
            messages.error(request, _("Veuillez vérifier la prestation sélectionnée."))

        return redirect("patients:consultation_detail", pk=consultation.pk)


class OrdonnanceCreateView(PersonnelMedicalRequiredMixin, View):
    """Création d'une ordonnance médicale depuis la consultation (avec contrôle strict can_prescribe)."""

    def post(self, request: Any, pk: Any):
        if not rbac_service.can_prescribe(request.user):
            raise PermissionDenied(_("Droit de prescription médicale non accordé."))

        consultation = get_object_or_404(Consultation, pk=pk)
        notes = request.POST.get("notes", "").strip()

        action = request.POST.get("action", "").strip()
        status = "DELIVERED" if action == "dispense" else "PENDING"
        delivered_at = timezone.now() if action == "dispense" else None
        delivered_by = request.user if action == "dispense" else None

        ordonnance = Ordonnance.objects.create(
            consultation=consultation,
            patient=consultation.patient,
            doctor=request.user,
            notes=notes,
            status=status,
            delivered_at=delivered_at,
            delivered_by=delivered_by,
        )

        # Récupération dynamique des lignes de médicaments transmises dans la requête
        medications = request.POST.getlist("medication_name")
        posologies = request.POST.getlist("posology")
        durations = request.POST.getlist("duration")
        quantities = request.POST.getlist("quantity")

        lines_created = 0
        for i in range(len(medications)):
            med_name = medications[i].strip() if i < len(medications) else ""
            if med_name:
                poso = posologies[i].strip() if i < len(posologies) else ""
                dur = durations[i].strip() if i < len(durations) else ""
                qty = int(quantities[i]) if (i < len(quantities) and quantities[i].isdigit()) else 1

                LigneOrdonnance.objects.create(
                    ordonnance=ordonnance,
                    medication_name=med_name,
                    posology=poso,
                    duration=dur,
                    quantity=qty,
                )
                lines_created += 1

        if action == "dispense":
            messages.success(
                request,
                _("L'ordonnance médicale a été générée et délivrée avec %(count)d médicament(s).")
                % {"count": lines_created},
            )
        else:
            messages.success(
                request,
                _("L'ordonnance médicale a été générée avec %(count)d médicament(s).")
                % {"count": lines_created},
            )
        return redirect("patients:consultation_detail", pk=consultation.pk)


class OrdonnanceDetailPrintView(PatientManagementRequiredMixin, DetailView):
    """Vue d'impression et d'export au format officiel / PDF d'une ordonnance médicale."""

    model = Ordonnance
    template_name = "patients/ordonnance_print.html"
    context_object_name = "ordonnance"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.all()
        return context


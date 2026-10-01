"""Vues de gestion des consultations médicales, prestations et prescriptions."""

from __future__ import annotations

from datetime import date
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
from django.views.generic import UpdateView

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
from utils.enums import PatientStatusEnum

User = get_user_model()


class DoctorAppointmentListView(PersonnelMedicalRequiredMixin, ListView):
    """Vue 'Mon Calendrier / Mes rendez-vous' conforme à la maquette officielle."""

    model = Appointment
    template_name = "patients/doctor_appointment_list.html"
    context_object_name = "appointments"
    paginate_by = 100

    def get_current_date(self) -> date:
        date_param = self.request.GET.get("date", "").strip()
        if date_param:
            try:
                return datetime.strptime(date_param, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass
        return timezone.now().date()

    def get_queryset(self) -> QuerySet[Appointment]:
        qs = Appointment.objects.select_related("patient", "doctor", "consultation")

        if not (self.request.user.is_superuser or self.request.user.is_proprietaire):
            qs = qs.filter(doctor=self.request.user)
        else:
            doctor_filter = self.request.GET.get("doctor", "").strip()
            if doctor_filter:
                try:
                    import uuid
                    uuid.UUID(doctor_filter)
                    qs = qs.filter(doctor_id=doctor_filter)
                except ValueError:
                    pass

        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)

        current_date = self.get_current_date()
        days_since_sunday = (current_date.weekday() + 1) % 7
        week_start = current_date - timedelta(days=days_since_sunday)
        week_end = week_start + timedelta(days=6)

        # Fenêtre temporelle élargie (mois entourant la semaine pour fluidité multi-vues)
        start_buffer = timezone.make_aware(datetime.combine(week_start - timedelta(days=14), datetime.min.time()))
        end_buffer = timezone.make_aware(datetime.combine(week_end + timedelta(days=14), datetime.max.time()))
        return qs.filter(scheduled_at__gte=start_buffer, scheduled_at__lte=end_buffer).order_by("scheduled_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        today = now.date()
        current_date = self.get_current_date()
        view_mode = self.request.GET.get("view", "week").strip()
        if view_mode not in ["week", "day", "month"]:
            view_mode = "week"

        # Calcul de la semaine Dimanche -> Samedi (identique à la maquette)
        days_since_sunday = (current_date.weekday() + 1) % 7
        week_start = current_date - timedelta(days=days_since_sunday)
        week_end = week_start + timedelta(days=6)

        french_months = [
            "", "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"
        ]
        french_days_short = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."]

        # Label de la période (ex: "janvier 11 – 17")
        if view_mode == "week":
            if week_start.month == week_end.month:
                period_label = f"{french_months[week_start.month]} {week_start.day} – {week_end.day}"
            else:
                period_label = f"{french_months[week_start.month]} {week_start.day} – {french_months[week_end.month]} {week_end.day}"
            if week_start.year != today.year:
                period_label += f" {week_start.year}"
        elif view_mode == "day":
            period_label = f"{current_date.day} {french_months[current_date.month]} {current_date.year}"
        else:
            period_label = f"{french_months[current_date.month]} {current_date.year}"

        # 7 colonnes pour la semaine
        week_days = []
        for i in range(7):
            d = week_start + timedelta(days=i)
            week_days.append({
                "date": d,
                "date_str": d.strftime("%Y-%m-%d"),
                "day_num": d.day,
                "day_short": french_days_short[i],
                "header_label": f"{d.day} {french_days_short[i]}",
                "is_today": (d == today),
                "is_selected": (d == current_date),
            })

        # Grille horaire 07:00 à 19:00 (comme sur la capture)
        hours_list = [f"{h:02d}:00" for h in range(7, 20)]

        # Rendez-vous sérialisés pour le moteur JS du calendrier
        appointments_qs = context["appointments"]
        serialized_appointments = []
        for rdv in appointments_qs:
            local_start = timezone.localtime(rdv.scheduled_at)
            local_end = timezone.localtime(rdv.end_time)

            color = "blue"
            if rdv.status in [AppointmentStatusEnum.COMPLETED, AppointmentStatusEnum.IN_CONSULTATION]:
                color = "emerald"
            elif "réunion" in rdv.reason.lower() or "staff" in rdv.reason.lower() or rdv.status == AppointmentStatusEnum.WAITING:
                color = "purple"
            elif rdv.status == AppointmentStatusEnum.CANCELLED:
                color = "rose"

            has_consultation = bool(getattr(rdv, "consultation", None))
            consultation_url = ""
            if has_consultation:
                consultation_url = reverse("patients:consultation_detail", kwargs={"pk": rdv.consultation.pk})
            else:
                consultation_url = reverse("patients:consultation_create") + f"?appointment={rdv.pk}"

            serialized_appointments.append({
                "id": str(rdv.pk),
                "patient_name": rdv.patient.full_name,
                "patient_id": str(rdv.patient.pk),
                "patient_number": rdv.patient.patient_number,
                "patient_url": rdv.patient.get_absolute_url(),
                "doctor_name": rdv.doctor.full_name,
                "doctor_id": str(rdv.doctor.pk),
                "date_str": local_start.strftime("%Y-%m-%d"),
                "start_time_str": local_start.strftime("%H:%M"),
                "end_time_str": local_end.strftime("%H:%M"),
                "time_range": f"{local_start.strftime('%H:%M')} – {local_end.strftime('%H:%M')}",
                "start_hour": local_start.hour,
                "start_minute": local_start.minute,
                "duration": rdv.estimated_duration_minutes,
                "reason": rdv.reason,
                "status": rdv.status,
                "status_display": rdv.get_status_display(),
                "color": color,
                "has_consultation": has_consultation,
                "consultation_url": consultation_url,
                "cancel_url": reverse("patients:appointment_cancel", kwargs={"pk": rdv.pk}),
                "status_update_url": reverse("patients:appointment_status_update", kwargs={"pk": rdv.pk}),
            })

        # Patients actifs et praticiens pour la modale de création sur créneau vide
        context["active_patients"] = Patient.objects.filter(
            status=PatientStatusEnum.ACTIVE
        ).order_by("last_name", "first_name")
        context["doctors"] = User.objects.filter(
            is_personnel_medical=True, is_active=True
        ).order_by("last_name", "first_name")
        context["default_doctor"] = self.request.user if getattr(self.request.user, "is_personnel_medical", False) else None

        # Navigation temporelle
        if view_mode == "week":
            prev_nav_date = (week_start - timedelta(days=7)).strftime("%Y-%m-%d")
            next_nav_date = (week_start + timedelta(days=7)).strftime("%Y-%m-%d")
        elif view_mode == "day":
            prev_nav_date = (current_date - timedelta(days=1)).strftime("%Y-%m-%d")
            next_nav_date = (current_date + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            # Mois précédent / Mois suivant
            first_of_month = current_date.replace(day=1)
            prev_month_last_day = first_of_month - timedelta(days=1)
            prev_nav_date = prev_month_last_day.replace(day=1).strftime("%Y-%m-%d")
            if first_of_month.month == 12:
                next_nav_date = first_of_month.replace(year=first_of_month.year + 1, month=1).strftime("%Y-%m-%d")
            else:
                next_nav_date = first_of_month.replace(month=first_of_month.month + 1).strftime("%Y-%m-%d")

        context["current_date"] = current_date
        context["current_date_str"] = current_date.strftime("%Y-%m-%d")
        context["today_date"] = today.strftime("%Y-%m-%d")
        context["view_mode"] = view_mode
        context["period_label"] = period_label
        context["week_start"] = week_start
        context["week_end"] = week_end
        context["week_days"] = week_days
        context["hours"] = hours_list
        context["prev_date"] = prev_nav_date
        context["next_date"] = next_nav_date
        context["serialized_appointments"] = serialized_appointments
        context["status_choices"] = AppointmentStatusEnum.choices
        context["selected_status"] = self.request.GET.get("status", "").strip()
        context["selected_doctor"] = self.request.GET.get("doctor", "").strip()

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


class ConsultationUpdateView(PersonnelMedicalRequiredMixin, UpdateView):
    """Modification d'une consultation médicale existante."""

    model = Consultation
    form_class = ConsultationForm
    template_name = "patients/consultation_form.html"

    def dispatch(self, request: Any, *args: Any, **kwargs: Any):
        consultation = self.get_object()
        if not (request.user.is_superuser or request.user.is_proprietaire):
            if consultation.doctor_id != request.user.id:
                raise PermissionDenied(_("Seul le médecin ayant créé la consultation peut la modifier."))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["patient"] = self.object.patient
        context["appointment"] = self.object.appointment
        context["is_update"] = True
        return context

    def form_valid(self, form: ConsultationForm):
        consultation = form.save()
        messages.success(
            self.request,
            _("La consultation pour %(patient)s a été mise à jour avec succès.")
            % {"patient": consultation.patient.full_name},
        )
        return redirect("patients:consultation_detail", pk=consultation.pk)


class PrestationRealiseeDeleteView(PersonnelMedicalRequiredMixin, View):
    """Suppression d'une prestation réalisée non encore facturée."""

    def post(self, request: Any, pk: Any, prestation_id: Any):
        consultation = get_object_or_404(Consultation, pk=pk)
        prestation_realisee = get_object_or_404(
            PrestationRealisee, pk=prestation_id, consultation=consultation
        )

        if prestation_realisee.status != "EN_ATTENTE_CAISSE":
            messages.error(
                request,
                _("Impossible de supprimer une prestation déjà facturée ou payée à la caisse."),
            )
            return redirect("patients:consultation_detail", pk=consultation.pk)

        name = prestation_realisee.prestation.name
        prestation_realisee.delete()
        messages.success(
            request,
            _("L'acte « %(name)s » a été retiré de la consultation.") % {"name": name},
        )
        return redirect("patients:consultation_detail", pk=consultation.pk)


class OrdonnanceUpdateView(PersonnelMedicalRequiredMixin, View):
    """Modification d'une ordonnance existante (autorisée tant qu'elle est en attente de délivrance)."""

    def get(self, request: Any, pk: Any):
        ordonnance = get_object_or_404(Ordonnance, pk=pk)
        if ordonnance.status != "PENDING":
            messages.error(
                request,
                _("Cette ordonnance a déjà été délivrée ou annulée et ne peut plus être modifiée."),
            )
            if ordonnance.consultation:
                return redirect("patients:consultation_detail", pk=ordonnance.consultation.pk)
            return redirect("patients:pharmacy_ordonnance_list")

        return redirect(
            f"{reverse('patients:consultation_detail', kwargs={'pk': ordonnance.consultation.pk})}#prescription-form"
            if ordonnance.consultation
            else reverse("patients:pharmacy_ordonnance_list")
        )

    def post(self, request: Any, pk: Any):
        ordonnance = get_object_or_404(Ordonnance, pk=pk)

        if not rbac_service.can_prescribe(request.user):
            raise PermissionDenied(_("Droit de prescription médicale non accordé."))

        if not (request.user.is_superuser or request.user.is_proprietaire):
            if ordonnance.doctor_id != request.user.id:
                raise PermissionDenied(_("Seul le médecin prescripteur peut modifier cette ordonnance."))

        if ordonnance.status != "PENDING":
            messages.error(
                request,
                _("Cette ordonnance a déjà été délivrée (%(status)s) et ne peut plus être modifiée pour des raisons de sécurité médicale.")
                % {"status": ordonnance.get_status_display()},
            )
            if ordonnance.consultation:
                return redirect("patients:consultation_detail", pk=ordonnance.consultation.pk)
            return redirect("patients:pharmacy_ordonnance_list")

        notes = request.POST.get("notes", "").strip()
        ordonnance.notes = notes
        ordonnance.save(update_fields=["notes", "updated_at"])

        # Remplacement des lignes de prescription
        medications = request.POST.getlist("medication_name")
        posologies = request.POST.getlist("posology")
        durations = request.POST.getlist("duration")
        quantities = request.POST.getlist("quantity")

        # Supprimer les anciennes lignes et réinsérer les nouvelles
        ordonnance.lines.all().delete()

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

        messages.success(
            request,
            _("L'ordonnance a été mise à jour avec succès (%(count)d médicament(s)).")
            % {"count": lines_created},
        )
        if ordonnance.consultation:
            return redirect("patients:consultation_detail", pk=ordonnance.consultation.pk)
        return redirect("patients:pharmacy_ordonnance_list")



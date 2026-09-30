"""Vues de gestion de l'agenda et des rendez-vous médicaux."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView
from django.views.generic import FormView
from django.views.generic import ListView

from apps.patients.forms import AppointmentCancelForm
from apps.patients.forms import AppointmentForm
from apps.patients.forms import AppointmentStatusForm
from apps.patients.models import Appointment
from apps.patients.models import Patient
from apps.patients.services import cancel_appointment
from apps.patients.services import create_appointment
from apps.patients.services import get_appointment_daily_stats
from apps.patients.services import update_appointment_status
from apps.users.mixins import PatientManagementRequiredMixin
from utils.enums import AppointmentStatusEnum

User = get_user_model()


class AppointmentListView(PatientManagementRequiredMixin, ListView):
    """Vue de planification et de suivi des rendez-vous médicaux avec filtres multi-critères."""

    model = Appointment
    template_name = "patients/appointment_list.html"
    context_object_name = "appointments"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[Appointment]:
        qs = Appointment.objects.select_related("patient", "doctor")

        # Recherche textuelle plein texte (Patient, NUP, Médecin, Motif)
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(patient__last_name__icontains=query)
                | Q(patient__first_name__icontains=query)
                | Q(patient__patient_number__icontains=query)
                | Q(reason__icontains=query)
                | Q(doctor__last_name__icontains=query)
                | Q(doctor__first_name__icontains=query)
            )

        # Filtre de date : soit date exacte choisie, soit plage temporelle rapide
        exact_date = self.request.GET.get("date", "").strip()
        if exact_date:
            try:
                parsed_date = datetime.strptime(exact_date, "%Y-%m-%d").date()
                qs = qs.filter(scheduled_at__date=parsed_date)
            except ValueError:
                pass
        else:
            date_filter = self.request.GET.get("date_filter", "all").strip()
            now = timezone.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timezone.timedelta(days=1)

            if date_filter == "today":
                qs = qs.filter(scheduled_at__gte=today_start, scheduled_at__lt=today_end)
            elif date_filter == "upcoming":
                qs = qs.filter(scheduled_at__gte=now)
            elif date_filter == "week":
                week_start = (now - timezone.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                week_end = week_start + timezone.timedelta(days=7)
                qs = qs.filter(scheduled_at__gte=week_start, scheduled_at__lt=week_end)
            elif date_filter == "month":
                month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if month_start.month == 12:
                    next_month = month_start.replace(year=month_start.year + 1, month=1)
                else:
                    next_month = month_start.replace(month=month_start.month + 1)
                qs = qs.filter(scheduled_at__gte=month_start, scheduled_at__lt=next_month)
            elif date_filter == "past":
                qs = qs.filter(scheduled_at__lt=now)
            # "all" conserve l'ensemble des rendez-vous

        # Filtre par praticien / médecin traitant
        doctor_id = self.request.GET.get("doctor", "").strip()
        if doctor_id:
            try:
                import uuid
                uuid.UUID(doctor_id)
                qs = qs.filter(doctor_id=doctor_id)
            except ValueError:
                pass

        # Filtre par statut clinique
        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)

        # Tri dynamique sécurisé
        ordering = self.request.GET.get("ordering", "").strip()
        allowed_orderings = {
            "scheduled_at": "scheduled_at",
            "-scheduled_at": "-scheduled_at",
            "patient__last_name": "patient__last_name",
            "-patient__last_name": "-patient__last_name",
        }
        if ordering in allowed_orderings:
            qs = qs.order_by(allowed_orderings[ordering])
        else:
            date_filter = self.request.GET.get("date_filter", "all").strip()
            if not exact_date and date_filter == "past":
                qs = qs.order_by("-scheduled_at")
            else:
                qs = qs.order_by("scheduled_at")

        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        date_filter = self.request.GET.get("date_filter", "all").strip() or "all"
        exact_date = self.request.GET.get("date", "").strip()
        selected_doctor = self.request.GET.get("doctor", "").strip()
        selected_status = self.request.GET.get("status", "").strip()
        default_ordering = "-scheduled_at" if (not exact_date and date_filter == "past") else "scheduled_at"
        selected_ordering = self.request.GET.get("ordering", default_ordering).strip()

        context["query"] = query
        context["date_filter"] = date_filter
        context["selected_date"] = exact_date
        context["selected_doctor"] = selected_doctor
        context["selected_status"] = selected_status
        context["selected_ordering"] = selected_ordering

        # Choix pour les listes déroulantes des filtres
        context["doctors"] = User.objects.filter(is_personnel_medical=True, is_active=True).order_by("last_name", "first_name")
        context["statuses"] = AppointmentStatusEnum.choices
        context["status_choices"] = AppointmentStatusEnum.choices
        context["date_filter_choices"] = [
            ("all", _("Toutes les dates")),
            ("today", _("Aujourd'hui")),
            ("upcoming", _("À venir")),
            ("week", _("Cette semaine")),
            ("month", _("Ce mois")),
            ("past", _("Historique / Passés")),
        ]
        context["ordering_choices"] = [
            ("scheduled_at", _("Date & heure croissante")),
            ("-scheduled_at", _("Date & heure décroissante")),
            ("patient__last_name", _("Nom du patient (A-Z)")),
            ("-patient__last_name", _("Nom du patient (Z-A)")),
        ]

        # Calcul du nombre de filtres actifs
        active_filters = 0
        if query:
            active_filters += 1
        if exact_date:
            active_filters += 1
        elif date_filter and date_filter != "all":
            active_filters += 1
        if selected_doctor:
            active_filters += 1
        if selected_status:
            active_filters += 1
        if selected_ordering and selected_ordering != default_ordering:
            active_filters += 1
        context["active_filters_count"] = active_filters

        context.update(get_appointment_daily_stats())
        return context


class AppointmentCreateView(PatientManagementRequiredMixin, SuccessMessageMixin, CreateView):
    """Planification d'un nouveau rendez-vous pour un patient."""

    model = Appointment
    form_class = AppointmentForm
    template_name = "patients/appointment_form.html"

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        patient_id = self.request.GET.get("patient")
        if patient_id:
            patient = get_object_or_404(Patient, pk=patient_id)
            initial["patient"] = patient
        return initial

    def form_valid(self, form: AppointmentForm):
        data = form.cleaned_data
        appointment = create_appointment(
            patient=data["patient"],
            doctor=data["doctor"],
            scheduled_at=data["scheduled_at"],
            estimated_duration_minutes=data["estimated_duration_minutes"] or 30,
            reason=data["reason"],
            notes=data.get("notes", ""),
            created_by=self.request.user,
        )
        self.object = appointment
        messages.success(
            self.request,
            _("Le rendez-vous pour %(patient)s avec Dr. %(doctor)s a été programmé pour le %(date)s.")
            % {
                "patient": appointment.patient.full_name,
                "doctor": appointment.doctor.full_name,
                "date": timezone.localtime(appointment.scheduled_at).strftime("%d/%m/%Y à %H:%M"),
            },
        )
        return redirect(appointment.patient.get_absolute_url())

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        patient_id = self.request.GET.get("patient")
        if patient_id:
            context["patient"] = get_object_or_404(Patient, pk=patient_id)
        return context


class AppointmentStatusUpdateView(PatientManagementRequiredMixin, View):
    """Action rapide de mise à jour du statut d'un rendez-vous (ex: En attente -> En consultation)."""

    def post(self, request: Any, pk: Any):
        appointment = get_object_or_404(Appointment, pk=pk)
        new_status = request.POST.get("status")
        next_url = request.POST.get("next") or reverse("patients:appointment_list")

        if new_status:
            from django.core.exceptions import ValidationError
            try:
                update_appointment_status(
                    appointment=appointment,
                    new_status=new_status,
                    updated_by=request.user,
                )
                messages.success(
                    request,
                    _("Le statut du rendez-vous de %(patient)s est désormais « %(status)s ».")
                    % {
                        "patient": appointment.patient.full_name,
                        "status": appointment.get_status_display(),
                    },
                )
            except ValidationError as exc:
                messages.error(request, str(exc.message if hasattr(exc, "message") else exc))

        return redirect(next_url)


class AppointmentCancelView(PatientManagementRequiredMixin, FormView):
    """Validation et confirmation de l'annulation d'un rendez-vous médical avec traçabilité du motif."""

    template_name = "patients/appointment_cancel.html"
    form_class = AppointmentCancelForm

    def dispatch(self, request: Any, *args: Any, **kwargs: Any):
        self.appointment = get_object_or_404(
            Appointment.objects.select_related("patient", "doctor"),
            pk=self.kwargs["pk"],
        )
        if self.appointment.status == AppointmentStatusEnum.CANCELLED:
            messages.info(
                request,
                _("Ce rendez-vous est déjà annulé."),
            )
            return redirect(self.get_success_url())
        if self.appointment.status == AppointmentStatusEnum.COMPLETED:
            messages.error(
                request,
                _("Impossible d'annuler un rendez-vous déjà honoré ou terminé."),
            )
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self) -> str:
        next_url = self.request.GET.get("next") or self.request.POST.get("next")
        if next_url:
            return next_url
        if hasattr(self, "appointment") and self.appointment.patient:
            return self.appointment.patient.get_absolute_url()
        return reverse("patients:appointment_list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["appointment"] = self.appointment
        context["patient"] = self.appointment.patient
        context["next_url"] = self.request.GET.get("next") or self.request.POST.get("next") or ""
        return context

    def form_valid(self, form: AppointmentCancelForm):
        reason = form.get_cancellation_reason()
        cancel_appointment(
            appointment=self.appointment,
            cancellation_reason=reason,
            cancelled_by=self.request.user,
        )
        messages.success(
            self.request,
            _("Le rendez-vous de %(patient)s prévu le %(date)s avec Dr. %(doctor)s a été annulé avec succès.")
            % {
                "patient": self.appointment.patient.full_name,
                "date": timezone.localtime(self.appointment.scheduled_at).strftime("%d/%m/%Y à %H:%M"),
                "doctor": self.appointment.doctor.full_name,
            },
        )
        return redirect(self.get_success_url())



"""Vues de gestion de l'agenda et des rendez-vous médicaux."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView
from django.views.generic import ListView

from apps.patients.forms import AppointmentForm
from apps.patients.forms import AppointmentStatusForm
from apps.patients.models import Appointment
from apps.patients.models import Patient
from apps.patients.services import create_appointment
from apps.patients.services import get_appointment_daily_stats
from apps.patients.services import update_appointment_status
from apps.users.mixins import PatientManagementRequiredMixin
from utils.enums import AppointmentStatusEnum


class AppointmentListView(PatientManagementRequiredMixin, ListView):
    """Vue de planification et de suivi des rendez-vous médicaux."""

    model = Appointment
    template_name = "patients/appointment_list.html"
    context_object_name = "appointments"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[Appointment]:
        qs = Appointment.objects.select_related("patient", "doctor").order_by("scheduled_at")
        date_filter = self.request.GET.get("date_filter", "today")

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timezone.timedelta(days=1)

        if date_filter == "today":
            qs = qs.filter(scheduled_at__gte=today_start, scheduled_at__lt=today_end)
        elif date_filter == "upcoming":
            qs = qs.filter(scheduled_at__gte=now)
        elif date_filter == "past":
            qs = qs.filter(scheduled_at__lt=now).order_by("-scheduled_at")
        # "all" shows everything

        doctor_id = self.request.GET.get("doctor")
        if doctor_id:
            qs = qs.filter(doctor_id=doctor_id)

        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)

        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["date_filter"] = self.request.GET.get("date_filter", "today")
        context["selected_status"] = self.request.GET.get("status", "")
        context.update(get_appointment_daily_stats())
        context["statuses"] = AppointmentStatusEnum.choices
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


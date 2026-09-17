"""Formulaires pour la création et la mise à jour des rendez-vous médicaux."""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.patients.models import Appointment
from apps.patients.models import Patient
from apps.patients.services.appointment_service import check_doctor_availability
from utils.enums import AppointmentStatusEnum
from utils.enums import PatientStatusEnum

User = get_user_model()


class AppointmentForm(forms.ModelForm):
    """Formulaire de planification de rendez-vous médical."""

    scheduled_at = forms.DateTimeField(
        label=_("Date et heure"),
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors bg-white",
            },
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = Appointment
        fields = [
            "patient",
            "doctor",
            "scheduled_at",
            "estimated_duration_minutes",
            "reason",
            "notes",
        ]
        widgets = {
            "patient": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors bg-white",
                }
            ),
            "doctor": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors bg-white",
                }
            ),
            "estimated_duration_minutes": forms.NumberInput(
                attrs={
                    "min": "5",
                    "step": "5",
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors",
                }
            ),
            "reason": forms.TextInput(
                attrs={
                    "placeholder": _("Ex: Consultation générale, Suivi tensionnel, Contrôle post-op..."),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": _("Notes ou consignes préalables (à jeun, apporter bilans antérieurs...)"),
                    "class": "w-full px-4 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors resize-none",
                }
            ),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Limite la liste des praticiens aux membres du personnel médical actifs
        self.fields["doctor"].queryset = User.objects.filter(
            is_personnel_medical=True,
            is_active=True,
        ).order_by("last_name", "first_name")
        self.fields["doctor"].label_from_instance = (
            lambda u: f"Dr. {u.full_name}" if u.full_name else u.email
        )

        # Limite aux patients avec dossier actif (suivi régulier)
        self.fields["patient"].queryset = Patient.objects.filter(
            status=PatientStatusEnum.ACTIVE
        ).order_by("last_name", "first_name")
        self.fields["patient"].label_from_instance = (
            lambda p: f"{p.patient_number} - {p.full_name}"
        )

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        doctor = cleaned_data.get("doctor")
        scheduled_at = cleaned_data.get("scheduled_at")
        duration = cleaned_data.get("estimated_duration_minutes") or 30

        if doctor and scheduled_at:
            exclude_id = self.instance.pk if self.instance and self.instance.pk else None
            is_available = check_doctor_availability(
                doctor=doctor,
                scheduled_at=scheduled_at,
                duration_minutes=duration,
                exclude_appointment_id=exclude_id,
            )
            if not is_available:
                self.add_error(
                    "scheduled_at",
                    _("Le Dr. %(doctor)s a déjà une consultation sur ce créneau horaire.")
                    % {"doctor": doctor.full_name},
                )

        return cleaned_data


class AppointmentStatusForm(forms.ModelForm):
    """Formulaire rapide de changement de statut pour le suivi de file d'attente."""

    class Meta:
        model = Appointment
        fields = ["status", "notes"]
        widgets = {
            "status": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] text-sm bg-white",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "w-full px-4 py-2 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] text-sm resize-none",
                }
            ),
        }


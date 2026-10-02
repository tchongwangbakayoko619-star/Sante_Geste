"""Formulaires pour la création et la mise à jour des rendez-vous médicaux."""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.db import models
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
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ],
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
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
                    "class": "searchable-select",
                    "data-searchable": "true",
                    "data-placeholder": _("Rechercher un patient (nom, prénom, matricule)..."),
                }
            ),
            "doctor": forms.Select(
                attrs={
                    "class": "searchable-select",
                    "data-searchable": "true",
                    "data-placeholder": _("Rechercher un médecin / praticien..."),
                }
            ),
            "estimated_duration_minutes": forms.NumberInput(
                attrs={
                    "min": "5",
                    "step": "5",
                }
            ),
            "reason": forms.TextInput(
                attrs={
                    "placeholder": _("Ex: Consultation générale, Suivi tensionnel, Contrôle post-op..."),
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": _("Notes ou consignes préalables (à jeun, apporter bilans antérieurs...)"),
                    "class": "resize-none",
                }
            ),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Limite la liste des praticiens aux membres du personnel médical actifs,
        # en préservant le praticien assigné pour consultation/édition d'un historique.
        doctor_filter = models.Q(is_personnel_medical=True, is_active=True)
        if self.instance and self.instance.pk and self.instance.doctor_id:
            doctor_filter |= models.Q(pk=self.instance.doctor_id)

        self.fields["doctor"].queryset = User.objects.filter(doctor_filter).order_by("last_name", "first_name")
        self.fields["doctor"].empty_label = _("Sélectionnez ou recherchez un praticien...")
        self.fields["doctor"].label_from_instance = (
            lambda u: f"Dr. {u.full_name}{' (Inactif)' if not u.is_active else ''}" if u.full_name else u.email
        )

        # Limite aux patients avec dossier actif (suivi régulier)
        self.fields["patient"].queryset = Patient.objects.filter(
            status=PatientStatusEnum.ACTIVE
        ).order_by("last_name", "first_name")
        self.fields["patient"].empty_label = _("Sélectionnez ou recherchez un patient...")
        self.fields["patient"].label_from_instance = (
            lambda p: f"{p.patient_number} - {p.full_name}"
        )

        # Initialise la durée sur 1 créneau (60 min) pour les nouveaux rendez-vous
        if "estimated_duration_minutes" in self.fields and not (self.instance and self.instance.pk):
            self.fields["estimated_duration_minutes"].initial = 60

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        doctor = cleaned_data.get("doctor")
        scheduled_at = cleaned_data.get("scheduled_at")
        duration = cleaned_data.get("estimated_duration_minutes") or 30

        if doctor:
            if not doctor.is_personnel_medical:
                self.add_error(
                    "doctor",
                    _("Ce professionnel n'est pas habilité comme personnel médical."),
                )
            elif not doctor.is_active:
                is_new = not self.instance or not self.instance.pk
                if is_new or self.instance.doctor_id != doctor.id:
                    self.add_error(
                        "doctor",
                        _("Ce praticien n'est plus en activité au sein de l'établissement. Impossible de lui assigner un rendez-vous."),
                    )

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


class AppointmentCancelForm(forms.Form):
    """Formulaire de validation et justification pour l'annulation d'un rendez-vous médical."""

    CANCELLATION_REASONS = [
        ("", _("Sélectionnez le motif de l'annulation...")),
        ("patient_request", _("Demande ou empêchement du patient")),
        ("patient_unreachable", _("Patient injoignable / Absence non signalée")),
        ("doctor_unavailable", _("Indisponibilité ou absence imprévue du praticien")),
        ("scheduling_error", _("Erreur de programmation / Doublon de créneau")),
        ("health_condition", _("Hospitalisation / Urgence médicale prioritaire")),
        ("other", _("Autre motif (à préciser)")),
    ]

    reason_category = forms.ChoiceField(
        choices=CANCELLATION_REASONS,
        label=_("Motif de l'annulation"),
        required=True,
        widget=forms.Select(),
    )

    reason_detail = forms.CharField(
        label=_("Précisions complémentaires"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": _("Précisez les circonstances de l'annulation ou toute consigne pour le suivi..."),
                "class": "resize-none",
            }
        ),
        help_text=_("Obligatoire si vous sélectionnez « Autre motif »."),
    )

    confirm_cancellation = forms.BooleanField(
        label=_("Je confirme l'annulation définitive de ce rendez-vous et la libération du créneau."),
        required=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 text-rose-600 focus:ring-rose-500 border-neutral-300 rounded cursor-pointer",
            }
        ),
    )

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        category = cleaned_data.get("reason_category")
        detail = (cleaned_data.get("reason_detail") or "").strip()

        if category == "other" and not detail:
            self.add_error(
                "reason_detail",
                _("Veuillez préciser la raison de l'annulation lorsque vous sélectionnez « Autre motif »."),
            )

        return cleaned_data

    def get_cancellation_reason(self) -> str:
        """Compose une chaîne explicite pour le service métier cancel_appointment."""
        category = self.cleaned_data.get("reason_category", "")
        detail = (self.cleaned_data.get("reason_detail") or "").strip()
        reasons_dict = dict(self.CANCELLATION_REASONS)
        category_label = str(reasons_dict.get(category, category))

        if detail:
            if category == "other":
                return detail
            return f"{category_label} : {detail}"
        return category_label



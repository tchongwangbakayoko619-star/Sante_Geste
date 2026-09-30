"""Formulaires pour la gestion des patients et des rendez-vous."""

from .appointment_forms import AppointmentCancelForm
from .appointment_forms import AppointmentForm
from .appointment_forms import AppointmentStatusForm
from .patient_forms import PatientAllergyForm
from .patient_forms import PatientForm
from .patient_forms import PatientMedicalUpdateForm
from .patient_forms import PatientSearchForm

__all__ = [
    "AppointmentCancelForm",
    "AppointmentForm",
    "AppointmentStatusForm",
    "PatientAllergyForm",
    "PatientForm",
    "PatientMedicalUpdateForm",
    "PatientSearchForm",
]


"""Vues pour la gestion des patients et des rendez-vous."""

from .appointment_views import AppointmentCreateView
from .appointment_views import AppointmentListView
from .appointment_views import AppointmentStatusUpdateView
from .patient_views import PatientAllergyCreateView
from .patient_views import PatientAllergyDeleteView
from .patient_views import PatientCreateView
from .patient_views import PatientDetailView
from .patient_views import PatientListView
from .patient_views import PatientMedicalUpdateView
from .patient_views import PatientUpdateView

__all__ = [
    "AppointmentCreateView",
    "AppointmentListView",
    "AppointmentStatusUpdateView",
    "PatientAllergyCreateView",
    "PatientAllergyDeleteView",
    "PatientCreateView",
    "PatientDetailView",
    "PatientListView",
    "PatientMedicalUpdateView",
    "PatientUpdateView",
]



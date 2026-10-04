"""Formulaires pour la gestion des patients et des rendez-vous."""

from .appointment_forms import AppointmentCancelForm
from .appointment_forms import AppointmentForm
from .appointment_forms import AppointmentStatusForm
from .consultation_forms import ConsultationForm
from .consultation_forms import FactureUpdateForm
from .consultation_forms import LigneOrdonnanceForm
from .consultation_forms import OrdonnanceForm
from .consultation_forms import PaiementForm
from .consultation_forms import PrestationRealiseeForm
from .patient_forms import PatientAllergyForm
from .patient_forms import PatientForm
from .patient_forms import PatientMedicalUpdateForm
from .patient_forms import PatientSearchForm

__all__ = [
    "AppointmentCancelForm",
    "AppointmentForm",
    "AppointmentStatusForm",
    "ConsultationForm",
    "FactureUpdateForm",
    "LigneOrdonnanceForm",
    "OrdonnanceForm",
    "PaiementForm",
    "PatientAllergyForm",
    "PatientForm",
    "PatientMedicalUpdateForm",
    "PatientSearchForm",
    "PrestationRealiseeForm",
]



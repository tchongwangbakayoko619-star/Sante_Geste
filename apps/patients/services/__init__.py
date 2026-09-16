"""Services métier pour le module patients et rendez-vous."""

from .appointment_service import check_doctor_availability
from .appointment_service import create_appointment
from .appointment_service import update_appointment_status
from .patient_service import create_patient
from .patient_service import generate_patient_number
from .patient_service import search_patients
from .patient_service import update_patient
from .patient_service import update_patient_medical_record

__all__ = [
    "check_doctor_availability",
    "create_appointment",
    "create_patient",
    "generate_patient_number",
    "search_patients",
    "update_appointment_status",
    "update_patient",
    "update_patient_medical_record",
]


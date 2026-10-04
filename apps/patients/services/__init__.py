"""Services métier pour le module patients et rendez-vous."""

from .appointment_service import cancel_appointment
from .appointment_service import check_doctor_availability
from .appointment_service import create_appointment
from .appointment_service import find_conflicting_appointment
from .appointment_service import get_appointment_daily_stats
from .appointment_service import reschedule_appointment
from .appointment_service import update_appointment_status
from .caisse_service import PaymentService
from .patient_service import add_patient_allergy
from .patient_service import check_allergy_contraindication
from .patient_service import create_patient
from .patient_service import generate_patient_number
from .patient_service import remove_patient_allergy
from .patient_service import search_patients
from .patient_service import update_patient
from .patient_service import update_patient_medical_record

__all__ = [
    "PaymentService",
    "add_patient_allergy",
    "cancel_appointment",
    "check_allergy_contraindication",
    "check_doctor_availability",
    "create_appointment",
    "create_patient",
    "find_conflicting_appointment",
    "generate_patient_number",
    "get_appointment_daily_stats",
    "remove_patient_allergy",
    "reschedule_appointment",
    "search_patients",
    "update_appointment_status",
    "update_patient",
    "update_patient_medical_record",
]

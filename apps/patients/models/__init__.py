"""Package de modèles pour l'application Patients & Rendez-vous."""

from apps.patients.models.appointment import Appointment
from apps.patients.models.caisse import Facture
from apps.patients.models.caisse import Paiement
from apps.patients.models.consultation import Consultation
from apps.patients.models.ordonnance import LigneOrdonnance
from apps.patients.models.ordonnance import Ordonnance
from apps.patients.models.patient import Allergen
from apps.patients.models.patient import Patient
from apps.patients.models.patient import PatientAllergy
from apps.patients.models.prestation import Prestation
from apps.patients.models.prestation import PrestationRealisee

__all__ = [
    "Patient",
    "Allergen",
    "PatientAllergy",
    "Appointment",
    "Consultation",
    "Prestation",
    "PrestationRealisee",
    "Ordonnance",
    "LigneOrdonnance",
    "Facture",
    "Paiement",
]

"""Application-wide enumerations."""

from django.db import models


class OTPPurposeEnum(models.TextChoices):
    """OTP Purposes enumeration."""

    REGISTRATION = "registration", "Inscription"
    PASSWORD_RESET = "password_reset", "Réinitialisation mot de passe"
    TWO_FACTOR = "two_factor", "Authentification à deux facteurs"


class UserRoleEnum(models.TextChoices):
    """Rôles applicatifs SantéGeste / CS² Health."""

    PERSONNEL_MEDICAL = "personnel_medical", "Personnel médical"
    PROPRIETAIRE = "proprietaire", "Propriétaire de l'établissement"
    RESPONSABLE_PHARMACIE = "responsable_pharmacie", "Responsable pharmacie"
    VENDEUR_PHARMACIE = "vendeur_pharmacie", "Vendeur pharmacie"
    CAISSIER = "caissier", "Caissier"
    AGENT_ACCUEIL = "agent_accueil", "Agent d'accueil"


class GenderEnum(models.TextChoices):
    """Genre / Sexe du patient."""

    MALE = "M", "Masculin"
    FEMALE = "F", "Féminin"
    OTHER = "O", "Autre"


class BloodGroupEnum(models.TextChoices):
    """Groupe sanguin et rhésus."""

    A_POSITIVE = "A+", "A+"
    A_NEGATIVE = "A-", "A-"
    B_POSITIVE = "B+", "B+"
    B_NEGATIVE = "B-", "B-"
    AB_POSITIVE = "AB+", "AB+"
    AB_NEGATIVE = "AB-", "AB-"
    O_POSITIVE = "O+", "O+"
    O_NEGATIVE = "O-", "O-"
    UNKNOWN = "UNKNOWN", "Non déterminé"


class AppointmentStatusEnum(models.TextChoices):
    """Statuts du cycle de vie d'un rendez-vous médical."""

    SCHEDULED = "scheduled", "Programmé"
    WAITING = "waiting", "En attente"
    IN_CONSULTATION = "in_consultation", "En consultation"
    COMPLETED = "completed", "Terminé"
    CANCELLED = "cancelled", "Annulé"
    MISSED = "missed", "Non honoré / Absent"


class AllergenCategoryEnum(models.TextChoices):
    """Catégories d'allergènes / substances selon les standards de santé."""

    MEDICATION = "medication", "Médicament / Molécule active"
    FOOD = "food", "Alimentaire"
    ENVIRONMENT = "environment", "Environnemental / Aéro-allergène"
    BIOLOGICAL = "biological", "Biologique / Latex / Venin"
    OTHER = "other", "Autre substance"


class AllergyCriticalityEnum(models.TextChoices):
    """Niveau de criticité d'une allergie (aligné sur FHIR AllergyIntoleranceCriticality)."""

    LOW = "low", "Faible (réaction mineure)"
    MODERATE = "moderate", "Modérée"
    HIGH = "high", "Élevée (Risque vital / Anaphylaxie)"
    UNABLE_TO_ASSESS = "unable_to_assess", "Indéterminée"


class AllergyVerificationStatusEnum(models.TextChoices):
    """Statut de vérification clinique de l'allergie (aligné sur FHIR)."""

    SUSPECTED = "suspected", "Suspectée / Déclarée par le patient"
    CONFIRMED = "confirmed", "Confirmée par bilan / Praticien"
    REFUTED = "refuted", "Réfutée / Erronée"


class PatientStatusEnum(models.TextChoices):
    """Statuts du cycle de vie clinique et administratif d'un patient (aligné FHIR/HL7)."""

    ACTIVE = "active", "Actif (Suivi en cours)"
    ARCHIVED = "archived", "Archivé (Dossier clos)"
    DECEASED = "deceased", "Décédé"
    TRANSFERRED = "transferred", "Transféré (Autre structure)"
    SUSPENDED = "suspended", "Suspendu (Identitovigilance / Litige)"



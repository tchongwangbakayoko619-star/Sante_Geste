"""Service de gestion des dossiers patients."""

from datetime import date
from typing import TYPE_CHECKING
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction
from django.db.models import Q
from django.db.models import QuerySet
from django.utils import timezone

from apps.patients.models import Allergen
from apps.patients.models import Patient
from apps.patients.models import PatientAllergy
from utils.enums import AllergyCriticalityEnum
from utils.enums import AllergyVerificationStatusEnum
from utils.phone import normalize_phone_number

if TYPE_CHECKING:
    from apps.users.models import User


def generate_patient_number() -> str:
    """Génère un numéro de dossier patient unique au format PAT-YYYY-XXXX.

    Utilise Patient.all_objects pour éviter toute réutilisation ou collision avec
    des dossiers supprimés logiquement (soft-delete).
    """
    current_year = timezone.now().year
    prefix = f"PAT-{current_year}-"

    with transaction.atomic():
        # Sélectionne les numéros de dossiers existants pour l'année en cours
        existing_numbers = (
            Patient.all_objects.filter(patient_number__startswith=prefix)
            .values_list("patient_number", flat=True)
            .order_by("-patient_number")
        )

        max_seq = 0
        for num in existing_numbers:
            parts = num.split("-")
            if len(parts) == 3 and parts[2].isdigit():
                seq = int(parts[2])
                if seq > max_seq:
                    max_seq = seq
                    break  # Étant ordonné par -patient_number, le premier est souvent le max si formatté à 4 chiffres

        next_seq = max_seq + 1
        return f"{prefix}{next_seq:04d}"


def create_patient(
    *,
    data: dict[str, Any],
    created_by: User | None = None,
    max_retries: int = 3,
) -> Patient:
    """Crée un nouveau dossier patient avec matricule unique.

    Intègre un mécanisme de réessai en cas de concurrence simultanée (race condition)
    sur la génération du numéro de matricule unique.
    """
    data_copy = dict(data)
    auto_generate = not bool(data_copy.get("patient_number"))

    for attempt in range(max_retries):
        if auto_generate:
            data_copy["patient_number"] = generate_patient_number()

        patient = Patient(**data_copy)
        if created_by:
            patient.set_created_by(created_by)
            patient.set_updated_by(created_by)

        try:
            patient.save()
            return patient
        except IntegrityError:
            # Si le matricule a été forcé manuellement ou si nous avons épuisé les tentatives
            if not auto_generate or attempt == max_retries - 1:
                raise


def update_patient(*, patient: Patient, data: dict[str, Any], updated_by: User | None = None) -> Patient:
    """Met à jour les informations d'un dossier patient."""
    # Empêche la modification accidentelle du matricule
    safe_data = {k: v for k, v in data.items() if k != "patient_number"}

    for field, value in safe_data.items():
        setattr(patient, field, value)

    if updated_by:
        patient.set_updated_by(updated_by)

    patient.save()
    return patient


def update_patient_medical_record(
    *,
    patient: Patient,
    data: dict[str, Any],
    updated_by: User | None = None,
) -> Patient:
    """Met à jour exclusivement les données médicales (allergies, affections chroniques, groupe sanguin).

    Réservé au personnel soignant habilité.
    """
    allowed_medical_fields = {"blood_group", "allergies", "chronic_diseases"}
    for field in allowed_medical_fields:
        if field in data:
            setattr(patient, field, data[field])

    if updated_by:
        patient.set_updated_by(updated_by)

    patient.save(update_fields=[*allowed_medical_fields, "updated_by", "updated_at"])
    return patient


def add_patient_allergy(
    *,
    patient: Patient,
    allergen: Allergen,
    criticality: str = AllergyCriticalityEnum.HIGH,
    verification_status: str = AllergyVerificationStatusEnum.CONFIRMED,
    reaction: str = "",
    diagnosed_date: date | None = None,
    notes: str = "",
    created_by: User | None = None,
) -> PatientAllergy:
    """Associe une allergie codifiée au dossier d'un patient."""
    allergy, created = PatientAllergy.objects.update_or_create(
        patient=patient,
        allergen=allergen,
        defaults={
            "criticality": criticality,
            "verification_status": verification_status,
            "reaction": reaction,
            "diagnosed_date": diagnosed_date,
            "notes": notes,
        },
    )
    if created_by:
        if created:
            allergy.set_created_by(created_by)
        allergy.set_updated_by(created_by)
        allergy.save()
    return allergy


def remove_patient_allergy(
    *,
    patient: Patient,
    allergen: Allergen,
) -> bool:
    """Supprime une allergie codifiée du dossier patient."""
    deleted_count, _ = PatientAllergy.objects.filter(
        patient=patient,
        allergen=allergen,
    ).delete()
    return deleted_count > 0


def check_allergy_contraindication(
    *,
    patient: Patient,
    atc_code: str = "",
    cross_reactivity_group: str = "",
    substance_name: str = "",
) -> list[PatientAllergy]:
    """Détecte les contre-indications allergiques pour une substance ou un médicament.

    Vérifie par code ATC partiel (famille médicamenteuse, ex: 'J01C' pour pénicillines),
    groupe de réactivité croisée ou nom de la substance.
    """
    contraindications = []
    patient_allergies = patient.patient_allergies.select_related("allergen").all()

    for pa in patient_allergies:
        allergen = pa.allergen
        # 1. Correspondance exacte ou partielle par nom de substance
        if substance_name and (
            substance_name.lower() in allergen.name.lower()
            or allergen.name.lower() in substance_name.lower()
        ):
            contraindications.append(pa)
            continue

        # 2. Correspondance par code ATC (ex: médicament débutant par J01C et allergie J01C)
        if atc_code and allergen.atc_code:
            if atc_code.startswith(allergen.atc_code) or allergen.atc_code.startswith(atc_code):
                contraindications.append(pa)
                continue

        # 3. Correspondance par groupe de réactivité croisée (ex: Bêta-lactamines, AINS)
        if cross_reactivity_group and allergen.cross_reactivity_group:
            if cross_reactivity_group.lower() == allergen.cross_reactivity_group.lower():
                contraindications.append(pa)
                continue

    return contraindications


def search_patients(query: str, *, active_only: bool = True) -> QuerySet[Patient]:
    """Recherche multi-critères rapide dans les dossiers patients avec normalisation téléphonique.

    Critères pris en charge :
    - Matricule exact ou partiel (PAT-...)
    - Nom et/ou prénom (recherche combinée)
    - Numéro de téléphone (recherche par format brut, format normalisé E.164 ou séquence numérique)
    - Email
    """
    qs = Patient.objects.all() if active_only else Patient.all_objects.all()
    cleaned_query = query.strip()
    if not cleaned_query:
        return qs

    # 1. Analyse téléphonique intelligente si la requête contient des chiffres
    phone_digits = "".join(c for c in cleaned_query if c.isdigit())
    phone_q = Q()
    if len(phone_digits) >= 3:
        try:
            normalized_query_phone = normalize_phone_number(cleaned_query)
            phone_q |= Q(phone_number__icontains=normalized_query_phone)
            phone_q |= Q(emergency_contact_phone__icontains=normalized_query_phone)
        except ValidationError:
            pass
        # Correspondance sur séquence de chiffres
        phone_q |= Q(phone_number__icontains=phone_digits)
        phone_q |= Q(emergency_contact_phone__icontains=phone_digits)

    # 2. Recherche textuelle multi-termes classique
    terms = cleaned_query.split()
    combined_text_q = Q()

    for term in terms:
        term_q = (
            Q(patient_number__icontains=term)
            | Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(phone_number__icontains=term)
            | Q(email__icontains=term)
        )
        combined_text_q &= term_q

    final_q = (combined_text_q | phone_q) if phone_q else combined_text_q
    return qs.filter(final_q).distinct()


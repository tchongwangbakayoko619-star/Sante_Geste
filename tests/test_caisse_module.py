"""Tests unitaires et d'intégration complets pour le MODULE CAISSE de SantéGeste."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.patients.models import Facture
from apps.patients.models import Paiement
from apps.patients.models import Patient
from apps.patients.models import Prestation
from apps.patients.models import PrestationRealisee
from apps.patients.services import PaymentService
from utils.enums import PatientStatusEnum

User = get_user_model()


@pytest.fixture
def caissier(db):
    """Utilisateur ayant le rôle Caissier."""
    return User.objects.create_user(
        email="caissier.test@cs2health.org",
        password="Password123!",
        first_name="Jean",
        last_name="Caissier",
        is_caissier=True,
    )


@pytest.fixture
def autre_caissier(db):
    """Second caissier pour tester l'attribution précise."""
    return User.objects.create_user(
        email="caissier2.test@cs2health.org",
        password="Password123!",
        first_name="Paul",
        last_name="SecondCaisse",
        is_caissier=True,
    )


@pytest.fixture
def medecin(db):
    """Médecin prescripteur d'actes."""
    return User.objects.create_user(
        email="docteur.test@cs2health.org",
        password="Password123!",
        first_name="Docteur",
        last_name="Soignant",
        is_personnel_medical=True,
    )


@pytest.fixture
def proprietaire(db):
    """Propriétaire / Administrateur de l'établissement."""
    return User.objects.create_user(
        email="proprio.test@cs2health.org",
        password="Password123!",
        first_name="Admin",
        last_name="Proprio",
        is_proprietaire=True,
    )


@pytest.fixture
def patient(db):
    """Patient enregistré dans la structure."""
    return Patient.objects.create(
        first_name="Amadou",
        last_name="Kouassi",
        date_of_birth="1990-05-15",
        gender="M",
        phone_number="+2250701020304",
        status=PatientStatusEnum.ACTIVE,
    )


@pytest.fixture
def acte_consultation(db):
    return Prestation.objects.create(
        name="Consultation Généraliste",
        code="CONS-GEN-01",
        category="CONSULTATION",
        standard_price=Decimal("8000.00"),
        is_active=True,
    )


@pytest.fixture
def acte_pansement(db):
    return Prestation.objects.create(
        name="Pansement Chirurgical",
        code="SOIN-PAN-01",
        category="SOIN",
        standard_price=Decimal("2000.00"),
        is_active=True,
    )


@pytest.mark.django_db
class TestCaisseModuleBusinessRules:
    """Suite de tests validant l'ensemble des règles métier exigées pour le module Caisse."""

    def test_1_nouvelle_facture_est_non_payee(
        self, patient, acte_consultation, medecin, caissier
    ):
        """Règle 1 : Une nouvelle facture générée est obligatoirement NON_PAYÉE avec montant payé = 0."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("8000.00"),
            status="EN_ATTENTE_CAISSE",
        )

        facture = PaymentService.create_invoice(
            patient=patient,
            prestations=[pr],
            cashier=caissier,
        )

        # Vérifications strictes
        assert facture.status == "UNPAID"
        assert facture.paid_amount == Decimal("0.00")
        assert facture.total_amount == Decimal("8000.00")
        assert facture.remaining_amount == Decimal("8000.00")
        assert facture.issued_by == caissier

        # Vérification des prestations liées
        pr.refresh_from_db()
        assert pr.status == "FACTURE"
        assert pr.facture == facture

    def test_2_caissier_peut_consulter_facture_et_liste(
        self, client, caissier, patient, acte_consultation, medecin
    ):
        """Règle 2 : Le Caissier peut consulter l'historique et le détail complet d'une facture."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("8000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        facture = PaymentService.create_invoice(
            patient=patient, prestations=[pr], cashier=caissier
        )

        client.force_login(caissier)

        # 1. Consultation de la liste des factures
        url_list = reverse("patients:facture_list")
        res_list = client.get(url_list)
        assert res_list.status_code == 200
        assert facture.invoice_number.encode() in res_list.content
        assert b"8000" in res_list.content

        # 2. Consultation du détail de la facture
        url_detail = reverse("patients:facture_detail", kwargs={"pk": facture.pk})
        res_detail = client.get(url_detail)
        assert res_detail.status_code == 200
        assert facture.invoice_number.encode() in res_detail.content
        assert patient.full_name.encode() in res_detail.content
        assert acte_consultation.name.encode() in res_detail.content
        assert b"Encaisser" in res_detail.content

    def test_3_paiement_complet_fait_passer_facture_a_payee(
        self, patient, acte_consultation, medecin, caissier
    ):
        """Règle 3 : Un paiement complet fait passer le statut de la facture à PAYÉE."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("8000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        facture = PaymentService.create_invoice(
            patient=patient, prestations=[pr], cashier=caissier
        )

        paiement = PaymentService.confirm_payment(
            facture=facture,
            amount=Decimal("8000.00"),
            payment_method="ESPECES",
            cashier=caissier,
            notes="Règlement complet en espèces",
        )

        facture.refresh_from_db()
        pr.refresh_from_db()

        assert facture.status == "PAID"
        assert facture.paid_amount == Decimal("8000.00")
        assert facture.remaining_amount == Decimal("0.00")
        assert pr.status == "PAYE"
        assert paiement.receipt_number.startswith("REC-")

    def test_4_paiement_partiel_fait_passer_facture_a_partiellement_payee(
        self, patient, acte_consultation, medecin, caissier
    ):
        """Règle 4 : Un paiement partiel fait passer la facture à PARTIELLEMENT_PAYÉE sans jamais la marquer PAYÉE."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("10000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        facture = PaymentService.create_invoice(
            patient=patient, prestations=[pr], cashier=caissier
        )

        # Montant reçu : 6 000 FCFA sur 10 000 FCFA
        paiement = PaymentService.confirm_payment(
            facture=facture,
            amount=Decimal("6000.00"),
            payment_method="MOBILE_MONEY",
            cashier=caissier,
        )

        facture.refresh_from_db()
        pr.refresh_from_db()

        assert facture.status == "PARTIALLY_PAID"
        assert facture.paid_amount == Decimal("6000.00")
        assert facture.remaining_amount == Decimal("4000.00")
        assert facture.status != "PAID"
        assert pr.status != "PAYE"  # Prestation pas encore totalement soldée

    def test_5_plusieurs_paiements_completent_une_facture(
        self, patient, acte_consultation, medecin, caissier
    ):
        """Règle 5 : Plusieurs paiements successifs peuvent compléter une facture jusqu'au solde total."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("10000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        facture = PaymentService.create_invoice(
            patient=patient, prestations=[pr], cashier=caissier
        )

        # 1er versement : 4 000 FCFA
        p1 = PaymentService.confirm_payment(
            facture=facture,
            amount=Decimal("4000.00"),
            payment_method="ESPECES",
            cashier=caissier,
        )
        facture.refresh_from_db()
        assert facture.status == "PARTIALLY_PAID"
        assert facture.remaining_amount == Decimal("6000.00")

        # 2ème versement : 6 000 FCFA (solde restant)
        p2 = PaymentService.confirm_payment(
            facture=facture,
            amount=Decimal("6000.00"),
            payment_method="CARTE",
            cashier=caissier,
        )
        facture.refresh_from_db()
        pr.refresh_from_db()

        assert facture.status == "PAID"
        assert facture.paid_amount == Decimal("10000.00")
        assert facture.remaining_amount == Decimal("0.00")
        assert pr.status == "PAYE"
        assert facture.paiements.count() == 2
        assert p1.receipt_number != p2.receipt_number

    def test_6_facture_totalement_payee_ne_peut_pas_etre_payee_une_seconde_fois(
        self, patient, acte_consultation, medecin, caissier
    ):
        """Règle 6 : Une facture totalement payée ne peut pas être payée à nouveau."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("5000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        facture = PaymentService.create_invoice(
            patient=patient, prestations=[pr], cashier=caissier
        )

        PaymentService.confirm_payment(
            facture=facture,
            amount=Decimal("5000.00"),
            payment_method="ESPECES",
            cashier=caissier,
        )
        facture.refresh_from_db()
        assert facture.status == "PAID"

        # Tentative d'un encaissement supplémentaire
        with pytest.raises(ValidationError) as exc:
            PaymentService.confirm_payment(
                facture=facture,
                amount=Decimal("1000.00"),
                payment_method="ESPECES",
                cashier=caissier,
            )
        assert "déjà intégralement réglée" in str(exc.value)

    def test_7_montant_nul_est_refuse(
        self, patient, acte_consultation, medecin, caissier
    ):
        """Règle 7 : Un montant de paiement nul (0 FCFA) est strictement refusé."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("5000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        facture = PaymentService.create_invoice(
            patient=patient, prestations=[pr], cashier=caissier
        )

        with pytest.raises(ValidationError) as exc:
            PaymentService.confirm_payment(
                facture=facture,
                amount=Decimal("0.00"),
                payment_method="ESPECES",
                cashier=caissier,
            )
        assert "strictement supérieur à zéro" in str(exc.value)

    def test_8_montant_negatif_est_refuse(
        self, patient, acte_consultation, medecin, caissier
    ):
        """Règle 8 : Un montant de paiement négatif est strictement refusé."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("5000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        facture = PaymentService.create_invoice(
            patient=patient, prestations=[pr], cashier=caissier
        )

        with pytest.raises(ValidationError) as exc:
            PaymentService.confirm_payment(
                facture=facture,
                amount=Decimal("-2000.00"),
                payment_method="ESPECES",
                cashier=caissier,
            )
        assert "strictement supérieur à zéro" in str(exc.value)

    def test_9_paiement_est_associe_au_bon_caissier(
        self, patient, acte_consultation, medecin, caissier, autre_caissier
    ):
        """Règle 9 : Le paiement est précisément associé au Caissier ayant réalisé l'opération."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("5000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        facture = PaymentService.create_invoice(
            patient=patient, prestations=[pr], cashier=caissier
        )

        # Encaissé par autre_caissier
        paiement = PaymentService.confirm_payment(
            facture=facture,
            amount=Decimal("5000.00"),
            payment_method="ESPECES",
            cashier=autre_caissier,
        )

        assert paiement.cashier == autre_caissier
        assert paiement.cashier != caissier

    def test_10_paiement_est_associe_a_la_bonne_facture(
        self, patient, acte_consultation, acte_pansement, medecin, caissier
    ):
        """Règle 10 : Le paiement est rigoureusement rattaché à la facture concernée."""
        pr1 = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("8000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        pr2 = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_pansement,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("2000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        f1 = PaymentService.create_invoice(
            patient=patient, prestations=[pr1], cashier=caissier
        )
        f2 = PaymentService.create_invoice(
            patient=patient, prestations=[pr2], cashier=caissier
        )

        p = PaymentService.confirm_payment(
            facture=f1,
            amount=Decimal("8000.00"),
            payment_method="ESPECES",
            cashier=caissier,
        )

        assert p.facture == f1
        assert p.facture != f2
        assert f1.paiements.count() == 1
        assert f2.paiements.count() == 0

    def test_11_recu_correspond_exactement_au_paiement_enregistre(
        self, client, patient, acte_consultation, medecin, caissier
    ):
        """Règle 11 : Le reçu généré correspond exactement au paiement enregistré (preuve de paiement distincte)."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("8000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        facture = PaymentService.create_invoice(
            patient=patient, prestations=[pr], cashier=caissier
        )

        paiement = PaymentService.confirm_payment(
            facture=facture,
            amount=Decimal("5000.00"),
            payment_method="MOBILE_MONEY",
            cashier=caissier,
            notes="Transaction Orange Money ID 987654",
        )

        assert paiement.receipt_number is not None
        assert paiement.receipt_number.startswith("REC-")

        # Accès à la vue de reçu
        client.force_login(caissier)
        url_recu = reverse("patients:paiement_receipt", kwargs={"pk": paiement.pk})
        res = client.get(url_recu)

        assert res.status_code == 200
        content = res.content.decode("utf-8")
        assert paiement.receipt_number in content
        assert facture.invoice_number in content
        assert patient.full_name in content
        assert "5000" in content
        assert "Mobile Money" in content
        assert caissier.full_name in content
        assert "Orange Money ID 987654" in content

    def test_12_facture_ne_peut_jamais_etre_marquee_payee_sans_paiement(
        self, patient, acte_consultation, medecin, caissier
    ):
        """Règle 12 : Une facture ne peut pas passer à PAYÉE sans encaissement valide, et le montant reçu ne peut pas dépasser le reste dû."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("8000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        facture = PaymentService.create_invoice(
            patient=patient, prestations=[pr], cashier=caissier
        )

        # Vérification 1 : Ne peut pas payer plus que le reste à payer
        with pytest.raises(ValidationError) as exc:
            PaymentService.confirm_payment(
                facture=facture,
                amount=Decimal("12000.00"),
                payment_method="ESPECES",
                cashier=caissier,
            )
        assert "ne peut pas dépasser le reste à payer" in str(exc.value)

        # La facture est restée intacte
        facture.refresh_from_db()
        assert facture.status == "UNPAID"
        assert facture.paid_amount == Decimal("0.00")

    def test_13_securite_caissier_ne_peut_pas_modifier_montant_facture(
        self, client, patient, acte_consultation, medecin, caissier
    ):
        """Règle de sécurité : Le Caissier n'a pas la permission de modifier arbitrairement le montant d'une facture."""
        pr = PrestationRealisee.objects.create(
            patient=patient,
            prestation=acte_consultation,
            doctor=medecin,
            quantity=1,
            unit_price=Decimal("8000.00"),
            status="EN_ATTENTE_CAISSE",
        )
        facture = PaymentService.create_invoice(
            patient=patient, prestations=[pr], cashier=caissier
        )

        client.force_login(caissier)
        url_update = reverse("patients:facture_update", kwargs={"pk": facture.pk})

        # Tentative de POST par le caissier
        res = client.post(url_update, {"total_amount": "5000"})
        # Doit être refusé (403 PermissionDenied car réservé au Propriétaire)
        assert res.status_code == 403

        # Le montant en base n'a pas changé
        facture.refresh_from_db()
        assert facture.total_amount == Decimal("8000.00")

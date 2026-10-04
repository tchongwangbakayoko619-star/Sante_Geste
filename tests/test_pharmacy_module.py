"""Tests complets pour le module Pharmacie de SantéGeste.

Couvre :
1. Produits, Catégories, Fournisseurs
2. Entrées de stock, traçabilité des mouvements
3. Stratégie FEFO (First Expired, First Out)
4. Workflow de vente et déstockage atomique
5. Intégration Caisse (Facture UNPAID créée)
6. Délivrance d'ordonnance médicale
7. Sécurité et contrôle d'accès RBAC (Responsable vs Vendeur vs Anonyme)
8. Annulation de vente et réintégration du stock
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.patients.models import Facture, LigneOrdonnance, Ordonnance, Patient
from apps.pharmacy.models import Batch, Category, Product, Sale, SaleItem, StockMovement, Supplier
from apps.pharmacy.services import SaleService, StockService
from utils.enums import PatientStatusEnum

User = get_user_model()


@pytest.fixture
def responsable_pharmacie(db):
    return User.objects.create_user(
        email="responsable.pharma@cs2health.org",
        password="Password123!",
        first_name="Alice",
        last_name="Pharma",
        is_responsable_pharmacie=True,
    )


@pytest.fixture
def vendeur_pharmacie(db):
    return User.objects.create_user(
        email="vendeur.pharma@cs2health.org",
        password="Password123!",
        first_name="Bob",
        last_name="Vendeur",
        is_vendeur_pharmacie=True,
    )


@pytest.fixture
def medecin(db):
    return User.objects.create_user(
        email="docteur.test@cs2health.org",
        password="Password123!",
        first_name="Dr",
        last_name="House",
        is_personnel_medical=True,
    )


@pytest.fixture
def patient(db):
    return Patient.objects.create(
        first_name="Mamadou",
        last_name="Diallo",
        patient_number="PAT-PHARMA-001",
        status=PatientStatusEnum.ACTIVE,
    )


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(
        name="Pharma Lab Cameroun",
        telephone="+237 677 00 11 22",
        email="contact@pharmalab.cm",
    )


@pytest.fixture
def product_paracetamol(db):
    return Product.objects.create(
        name="Paracétamol",
        dci="Paracétamol",
        dosage="500 mg",
        form="Comprimé",
        reference_code="MED-PARA-500",
        purchase_price=Decimal("100.00"),
        selling_price=Decimal("250.00"),
        min_stock_threshold=20,
        current_stock=0,
    )


# ==============================================================================
# TESTS 1 : ENTRÉE DE STOCK & FEFO
# ==============================================================================

@pytest.mark.django_db
def test_stock_entry_and_movement_creation(responsable_pharmacie, product_paracetamol, supplier):
    """Test 1: Une réception fournisseur augmente le stock et crée le mouvement IN_PURCHASE."""
    exp_date = date.today() + timedelta(days=365)
    batch = StockService.receive_batch(
        product=product_paracetamol,
        batch_number="LOT-2026-001",
        expiry_date=exp_date,
        quantity=100,
        purchase_price=Decimal("100.00"),
        user=responsable_pharmacie,
        supplier=supplier,
        selling_price=Decimal("250.00"),
    )

    product_paracetamol.refresh_from_db()
    assert product_paracetamol.current_stock == 100
    assert batch.current_quantity == 100
    assert batch.status == "ACTIVE"

    # Vérification du mouvement
    movement = StockMovement.objects.filter(product=product_paracetamol).first()
    assert movement is not None
    assert movement.movement_type == "IN_PURCHASE"
    assert movement.quantity == 100
    assert movement.previous_stock == 0
    assert movement.new_stock == 100
    assert movement.user == responsable_pharmacie


@pytest.mark.django_db
def test_fefo_allocation_strategy(responsable_pharmacie, product_paracetamol, supplier):
    """Test 2: La stratégie FEFO privilégie le lot dont la date de péremption est la plus proche."""
    today = date.today()

    # Lot 1 : Expire dans 30 jours (50 unités)
    StockService.receive_batch(
        product=product_paracetamol,
        batch_number="LOT-EARLY",
        expiry_date=today + timedelta(days=30),
        quantity=50,
        purchase_price=Decimal("100.00"),
        user=responsable_pharmacie,
        supplier=supplier,
    )

    # Lot 2 : Expire dans 180 jours (100 unités)
    StockService.receive_batch(
        product=product_paracetamol,
        batch_number="LOT-LATER",
        expiry_date=today + timedelta(days=180),
        quantity=100,
        purchase_price=Decimal("100.00"),
        user=responsable_pharmacie,
        supplier=supplier,
    )

    product_paracetamol.refresh_from_db()
    assert product_paracetamol.current_stock == 150

    # Demande de 20 unités -> Doit être entièrement prélevé sur LOT-EARLY
    allocations_1 = StockService.allocate_stock_fefo(product_paracetamol, 20)
    assert len(allocations_1) == 1
    assert allocations_1[0]["batch"].batch_number == "LOT-EARLY"
    assert allocations_1[0]["quantity"] == 20

    # Demande de 70 unités -> Doit prélever 50 sur LOT-EARLY et 20 sur LOT-LATER
    allocations_2 = StockService.allocate_stock_fefo(product_paracetamol, 70)
    assert len(allocations_2) == 2
    assert allocations_2[0]["batch"].batch_number == "LOT-EARLY"
    assert allocations_2[0]["quantity"] == 50
    assert allocations_2[1]["batch"].batch_number == "LOT-LATER"
    assert allocations_2[1]["quantity"] == 20


@pytest.mark.django_db
def test_expired_batches_are_not_allocated(responsable_pharmacie, product_paracetamol, supplier):
    """Test 3: Un lot déjà périmé ne peut pas être alloué pour une vente."""
    today = date.today()
    # Création directe d'un lot périmé
    b_expired = Batch.objects.create(
        product=product_paracetamol,
        batch_number="LOT-PERIME",
        expiry_date=today - timedelta(days=5),
        initial_quantity=50,
        current_quantity=50,
        status="ACTIVE",
    )
    product_paracetamol.current_stock = 50
    product_paracetamol.save()

    # Tentative d'allocation -> doit lever ValidationError pour stock non périmé insuffisant
    with pytest.raises(ValidationError) as exc:
        StockService.allocate_stock_fefo(product_paracetamol, 10)
    assert "Stock insuffisant" in str(exc.value)


# ==============================================================================
# TESTS 2 : WORKFLOW DE VENTE & CAISSE
# ==============================================================================

@pytest.mark.django_db
def test_sale_creation_and_caisse_integration(vendeur_pharmacie, product_paracetamol, patient, supplier):
    """Test 4: La vente déstocke selon FEFO, crée la facture Caisse UNPAID et trace les mouvements."""
    # Approvisionner 100 unités
    StockService.receive_batch(
        product=product_paracetamol,
        batch_number="LOT-2026-X",
        expiry_date=date.today() + timedelta(days=200),
        quantity=100,
        purchase_price=Decimal("100.00"),
        selling_price=Decimal("250.00"),
        user=vendeur_pharmacie,
        supplier=supplier,
    )

    # Réaliser une vente de 10 unités à 250 FCFA (total 2500 FCFA)
    items_data = [{"product": product_paracetamol, "quantity": 10}]
    sale = SaleService.create_sale(
        seller=vendeur_pharmacie,
        items_data=items_data,
        patient=patient,
    )

    product_paracetamol.refresh_from_db()
    assert product_paracetamol.current_stock == 90
    assert sale.total_amount == Decimal("2500.00")
    assert sale.status == "PENDING_PAYMENT"

    # Vérification Facture Caisse créée au statut UNPAID
    assert sale.facture is not None
    assert sale.facture.patient == patient
    assert sale.facture.total_amount == Decimal("2500.00")
    assert sale.facture.status == "UNPAID"
    assert sale.facture.paid_amount == Decimal("0.00")

    # Mouvement de stock OUT_SALE
    mov = StockMovement.objects.filter(product=product_paracetamol, movement_type="OUT_SALE").first()
    assert mov is not None
    assert mov.quantity == -10
    assert mov.new_stock == 90


@pytest.mark.django_db
def test_prescription_dispensing_sale(vendeur_pharmacie, medecin, patient, product_paracetamol, supplier):
    """Test 5: La délivrance sur ordonnance clôture la prescription médicale."""
    StockService.receive_batch(
        product=product_paracetamol,
        batch_number="LOT-MED",
        expiry_date=date.today() + timedelta(days=200),
        quantity=50,
        purchase_price=Decimal("100.00"),
        user=vendeur_pharmacie,
        supplier=supplier,
    )

    # Créer une ordonnance
    ord_obj = Ordonnance.objects.create(
        patient=patient,
        doctor=medecin,
        status="PENDING",
    )
    LigneOrdonnance.objects.create(
        ordonnance=ord_obj,
        medication_name="Paracétamol",
        posology="1 cp matin et soir",
        duration="3 jours",
        quantity="2",
    )

    sale = SaleService.create_sale(
        seller=vendeur_pharmacie,
        items_data=[{"product": product_paracetamol, "quantity": 2}],
        ordonnance=ord_obj,
        patient=patient,
    )

    ord_obj.refresh_from_db()
    assert ord_obj.status == "DELIVERED"
    assert ord_obj.delivered_by == vendeur_pharmacie
    assert sale.ordonnance == ord_obj


@pytest.mark.django_db
def test_sale_cancellation_restores_stock(responsable_pharmacie, vendeur_pharmacie, product_paracetamol, supplier, patient):
    """Test 6: L'annulation d'une vente réintègre les quantités en stock et annule la facture."""
    StockService.receive_batch(
        product=product_paracetamol,
        batch_number="LOT-RESTORE",
        expiry_date=date.today() + timedelta(days=100),
        quantity=50,
        purchase_price=Decimal("100.00"),
        user=responsable_pharmacie,
        supplier=supplier,
    )

    sale = SaleService.create_sale(
        seller=vendeur_pharmacie,
        items_data=[{"product": product_paracetamol, "quantity": 10}],
        patient=patient,
    )
    product_paracetamol.refresh_from_db()
    assert product_paracetamol.current_stock == 40

    # Annulation par le Responsable
    SaleService.cancel_sale(sale=sale, user=responsable_pharmacie, reason="Erreur de saisie client")

    product_paracetamol.refresh_from_db()
    sale.refresh_from_db()
    assert product_paracetamol.current_stock == 50
    assert sale.status == "CANCELLED"
    assert sale.facture.status == "CANCELLED"


# ==============================================================================
# TESTS 3 : CONTRÔLE D'ACCÈS RBAC SERVEUR
# ==============================================================================

@pytest.mark.django_db
def test_rbac_vendeur_cannot_adjust_stock(client, vendeur_pharmacie, product_paracetamol):
    """Test 7: Le vendeur ne peut pas accéder aux ajustements de stock (HTTP 403)."""
    client.force_login(vendeur_pharmacie)
    url_adjust = reverse("pharmacy:stock_adjustment")
    response = client.get(url_adjust)
    assert response.status_code == 403


@pytest.mark.django_db
def test_rbac_vendeur_cannot_create_product(client, vendeur_pharmacie):
    """Test 8: Le vendeur ne peut pas créer de nouveaux produits (HTTP 403)."""
    client.force_login(vendeur_pharmacie)
    url_create = reverse("pharmacy:product_create")
    response = client.get(url_create)
    assert response.status_code == 403


@pytest.mark.django_db
def test_rbac_responsable_can_manage_stock_and_products(client, responsable_pharmacie, product_paracetamol):
    """Test 9: Le responsable peut accéder aux écrans de gestion et au catalogue."""
    client.force_login(responsable_pharmacie)
    res_list = client.get(reverse("pharmacy:product_list"))
    assert res_list.status_code == 200

    res_entry = client.get(reverse("pharmacy:stock_entry"))
    assert res_entry.status_code == 200

    res_adjust = client.get(reverse("pharmacy:stock_adjustment"))
    assert res_adjust.status_code == 200


@pytest.mark.django_db
def test_rbac_unauthenticated_or_other_roles_cannot_access_pharmacy(client, medecin):
    """Test 10: Un médecin ou utilisateur sans rôle pharmacie ne peut pas accéder aux ventes pharmacie."""
    client.force_login(medecin)
    response = client.get(reverse("pharmacy:sale_create"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_sidebar_responsable_vs_vendeur_navigation(client, responsable_pharmacie, vendeur_pharmacie):
    """Test 11: Vérification de la structure exacte de la sidebar pour Responsable et Vendeur."""
    # 1. Responsable Pharmacie
    client.force_login(responsable_pharmacie)
    res_resp = client.get(reverse("pharmacy:dashboard"))
    assert res_resp.status_code == 200
    content_resp = res_resp.content.decode("utf-8")
    sidebar_resp = content_resp.split('id="dashboard-sidebar"')[1].split('</aside>')[0]
    
    # Doit contenir les groupes complets dans la sidebar
    assert "Stock" in sidebar_resp
    assert "Lots" in sidebar_resp
    assert "Mouvements" in sidebar_resp
    assert "Inventaire" in sidebar_resp
    assert "Approvisionnement" in sidebar_resp
    assert "Fournisseurs" in sidebar_resp
    assert "Entrées de stock" in sidebar_resp
    assert "Délivrance" in sidebar_resp
    assert "Prescriptions" in sidebar_resp
    assert "Délivrances" in sidebar_resp
    assert "Ventes" in sidebar_resp
    assert "Nouvelle vente" in sidebar_resp
    assert "Historique" in sidebar_resp
    assert "Rapports" in sidebar_resp
    assert "Paramètres" in sidebar_resp
    assert "Rapports &amp; Exports" in sidebar_resp or "Rapports & Exports" in sidebar_resp

    # 2. Vendeur Pharmacie
    client.force_login(vendeur_pharmacie)
    res_vend = client.get(reverse("pharmacy:dashboard"))
    assert res_vend.status_code == 200
    content_vend = res_vend.content.decode("utf-8")
    sidebar_vend = content_vend.split('id="dashboard-sidebar"')[1].split('</aside>')[0]
    pharmacy_submenu_vend = sidebar_vend.split('id="pharmacy-submenu"')[1].split('<!-- Item 6:')[0]

    # Le vendeur voit les fonctions autorisées dans sa sidebar pharmacie
    assert "Tableau de bord" in pharmacy_submenu_vend
    assert "Produits" in pharmacy_submenu_vend
    assert "Prescriptions" in pharmacy_submenu_vend
    assert "Délivrances" in pharmacy_submenu_vend
    assert "Nouvelle vente" in pharmacy_submenu_vend
    assert "Historique" in pharmacy_submenu_vend
    # Le vendeur ne doit PAS voir les fonctions d'administration du responsable dans la sidebar pharmacie
    assert "Lots" not in pharmacy_submenu_vend
    assert "Mouvements" not in pharmacy_submenu_vend
    assert "Inventaire" not in pharmacy_submenu_vend
    assert "Fournisseurs" not in pharmacy_submenu_vend
    assert "Entrées de stock" not in pharmacy_submenu_vend
    assert "Paramètres" not in pharmacy_submenu_vend
    assert "Rapports" not in pharmacy_submenu_vend


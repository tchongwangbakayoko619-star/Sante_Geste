"""Tests unitaires exhaustifs pour le système de contrôle d'accès basé sur les rôles (RBAC).

Couvre :
- Normalisation et validation des rôles
- Rôles directs vs rôles effectifs
- Héritage métier (Responsable Pharmacie -> Vendeur Pharmacie)
- Séparation des pouvoirs (Prescription médicale stricte, Caisse)
- Méthodes et propriétés du modèle User
- Mixins CBV (RoleRequiredMixin et spécialisés)
- Décorateurs FBV (role_required et raccourcis)
- Filtres et balises de gabarit (rbac_tags)
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.template import Context, Template
from django.test import RequestFactory
from django.views.generic import View

from apps.users.decorators import (
    agent_accueil_required,
    caissier_required,
    patient_management_required,
    personnel_medical_required,
    pharmacy_access_required,
    proprietaire_required,
    responsable_pharmacie_required,
    role_required,
    vendeur_pharmacie_required,
)
from apps.users.mixins import (
    AgentAccueilRequiredMixin,
    CaissierRequiredMixin,
    PatientManagementRequiredMixin,
    PersonnelMedicalRequiredMixin,
    PharmacyAccessRequiredMixin,
    ProprietaireRequiredMixin,
    ResponsablePharmacieRequiredMixin,
    RoleRequiredMixin,
    VendeurPharmacieRequiredMixin,
)
from apps.users.services.rbac import (
    _is_active_authenticated_user,
    can_manage_cash,
    can_manage_patients,
    can_manage_pharmacy,
    can_prescribe,
    can_sell_pharmacy,
    can_validate_sensitive_ops,
    check_user_roles,
    get_direct_roles,
    get_effective_roles,
    has_all_roles,
    has_role,
    normalize_role,
)
from utils.enums import UserRoleEnum

User = get_user_model()
pytestmark = pytest.mark.django_db


# =============================================================================
# 0. Helper interne d'authentification et d'activité
# =============================================================================

def test_is_active_authenticated_user_helper() -> None:
    """Vérifie le fonctionnement unitaire du helper interne _is_active_authenticated_user."""
    # Cas 1: None
    assert _is_active_authenticated_user(None) is False

    # Cas 2: AnonymousUser
    anon = AnonymousUser()
    assert _is_active_authenticated_user(anon) is False

    # Cas 3: Utilisateur inactif (is_active=False)
    inactive = User.objects.create_user(
        email="inactive.helper@santegeste.com",
        password="Password123!",
        is_active=False,
    )
    assert _is_active_authenticated_user(inactive) is False

    # Cas 4: Objet factice non authentifié mais actif
    class DummyInactiveAuthUser:
        is_authenticated = False
        is_active = True

    assert _is_active_authenticated_user(DummyInactiveAuthUser()) is False

    # Cas 5: Utilisateur authentifié et actif
    active = User.objects.create_user(
        email="active.helper@santegeste.com",
        password="Password123!",
        is_active=True,
    )
    assert _is_active_authenticated_user(active) is True


# =============================================================================
# 1. Normalisation des rôles
# =============================================================================

def test_normalize_role_valid() -> None:
    """Vérifie la normalisation des enums et des chaînes de valeur valides."""
    assert normalize_role(UserRoleEnum.PROPRIETAIRE) == UserRoleEnum.PROPRIETAIRE
    assert normalize_role("proprietaire") == UserRoleEnum.PROPRIETAIRE
    assert normalize_role("personnel_medical") == UserRoleEnum.PERSONNEL_MEDICAL


def test_normalize_role_invalid() -> None:
    """Vérifie qu'un rôle non répertorié ou en majuscules (nom d'enum) lève ValueError."""
    with pytest.raises(ValueError, match="n'est pas un rôle valide"):
        normalize_role("super_admin")

    with pytest.raises(ValueError, match="n'est pas un rôle valide"):
        normalize_role("PROPRIETAIRE")


# =============================================================================
# 2. Rôles directs vs effectifs & Héritage métier
# =============================================================================

def test_anonymous_and_inactive_users_have_no_roles() -> None:
    """Un utilisateur anonyme ou inactif ne doit avoir aucun rôle effectif ni direct."""
    anon = AnonymousUser()
    assert get_direct_roles(anon) == set()
    assert get_effective_roles(anon) == set()
    assert has_role(anon, UserRoleEnum.PROPRIETAIRE) is False

    inactive_user = User.objects.create_user(
        email="inactive@santegeste.com",
        password="Password123!",
        is_active=False,
        is_proprietaire=True,
    )
    assert get_direct_roles(inactive_user) == set()
    assert get_effective_roles(inactive_user) == set()
    assert has_role(inactive_user, UserRoleEnum.PROPRIETAIRE) is False
    assert inactive_user.has_role("proprietaire") is False


def test_role_inheritance_responsable_pharmacie() -> None:
    """Vérifie que le Responsable Pharmacie hérite automatiquement du rôle Vendeur Pharmacie."""
    resp = User.objects.create_user(
        email="pharmacien.chef@santegeste.com",
        password="Password123!",
        is_responsable_pharmacie=True,
        is_vendeur_pharmacie=False,
    )

    # Rôles directs : uniquement responsable pharmacie
    direct = resp.get_direct_roles()
    assert direct == {UserRoleEnum.RESPONSABLE_PHARMACIE}
    assert resp.active_roles == ["responsable_pharmacie"]

    # Rôles effectifs : responsable pharmacie + vendeur pharmacie
    effective = resp.get_effective_roles()
    assert UserRoleEnum.RESPONSABLE_PHARMACIE in effective
    assert UserRoleEnum.VENDEUR_PHARMACIE in effective

    # has_role
    assert resp.has_role(UserRoleEnum.RESPONSABLE_PHARMACIE) is True
    assert resp.has_role(UserRoleEnum.VENDEUR_PHARMACIE) is True
    assert resp.has_role("vendeur_pharmacie") is True
    assert resp.has_role(UserRoleEnum.CAISSIER) is False

    # has_all_roles
    assert resp.has_all_roles("responsable_pharmacie", "vendeur_pharmacie") is True
    assert resp.has_all_roles("responsable_pharmacie", "caissier") is False


def test_vendeur_pharmacie_does_not_inherit_responsable() -> None:
    """Un simple vendeur pharmacie n'a PAS le rôle responsable pharmacie."""
    vendeur = User.objects.create_user(
        email="vendeur@santegeste.com",
        password="Password123!",
        is_vendeur_pharmacie=True,
        is_responsable_pharmacie=False,
    )
    assert vendeur.has_role("vendeur_pharmacie") is True
    assert vendeur.has_role("responsable_pharmacie") is False
    assert vendeur.can_sell_pharmacy is True
    assert vendeur.can_manage_pharmacy is False


def test_superuser_has_all_effective_roles() -> None:
    """Un superuser actif possède tous les rôles applicatifs configurés."""
    admin = User.objects.create_superuser(
        email="admin@santegeste.com",
        password="Password123!",
    )
    from apps.users.services.rbac import ROLE_FIELD_MAP

    assert get_effective_roles(admin) == set(ROLE_FIELD_MAP.keys())
    assert admin.has_role(UserRoleEnum.CAISSIER) is True
    assert admin.has_role(UserRoleEnum.PROPRIETAIRE) is True
    assert admin.has_all_roles(
        UserRoleEnum.PROPRIETAIRE, UserRoleEnum.CAISSIER, UserRoleEnum.AGENT_ACCUEIL
    ) is True


# =============================================================================
# 3. Séparation des pouvoirs & Prédicats transverses
# =============================================================================

def test_separation_of_powers_can_prescribe() -> None:
    """Règle critique : la prescription médicale est STRICTEMENT réservée au personnel médical.

    Le propriétaire ou superuser n'a PAS le droit de prescription s'il n'est pas praticien.
    """
    proprio = User.objects.create_user(
        email="proprio@santegeste.com",
        password="Password123!",
        is_proprietaire=True,
    )
    assert proprio.can_prescribe is False
    assert can_prescribe(proprio) is False

    admin = User.objects.create_superuser(
        email="root@santegeste.com",
        password="Password123!",
    )
    assert admin.can_prescribe is False

    doctor = User.objects.create_user(
        email="docteur@santegeste.com",
        password="Password123!",
        is_personnel_medical=True,
    )
    assert doctor.can_prescribe is True
    assert can_prescribe(doctor) is True


def test_separation_of_powers_cash_and_sensitive_ops() -> None:
    """Le propriétaire ne gère pas la caisse au jour le jour (sauf s'il est caissier).

    De même, les opérations sensibles sont réservées au propriétaire (le superuser ne peut pas valider).
    """
    proprio = User.objects.create_user(
        email="proprio.ops@santegeste.com",
        password="Password123!",
        is_proprietaire=True,
    )
    assert proprio.can_validate_sensitive_ops is True
    assert can_validate_sensitive_ops(proprio) is True
    assert proprio.can_manage_cash is False

    caissier = User.objects.create_user(
        email="caissier@santegeste.com",
        password="Password123!",
        is_caissier=True,
    )
    assert caissier.can_manage_cash is True
    assert caissier.can_validate_sensitive_ops is False
    assert can_validate_sensitive_ops(caissier) is False

    admin = User.objects.create_superuser(
        email="root.ops@santegeste.com",
        password="Password123!",
    )
    # Séparation des pouvoirs : le superuser ne peut pas valider les opérations sensibles
    assert admin.can_validate_sensitive_ops is False
    assert can_validate_sensitive_ops(admin) is False


def test_can_manage_patients() -> None:
    """Accessible à l'agent d'accueil ET au personnel médical."""
    agent = User.objects.create_user(
        email="accueil@santegeste.com",
        password="Password123!",
        is_agent_accueil=True,
    )
    med = User.objects.create_user(
        email="infirmier@santegeste.com",
        password="Password123!",
        is_personnel_medical=True,
    )
    vendeur = User.objects.create_user(
        email="pharma@santegeste.com",
        password="Password123!",
        is_vendeur_pharmacie=True,
    )
    assert agent.can_manage_patients is True
    assert med.can_manage_patients is True
    assert vendeur.can_manage_patients is False


# =============================================================================
# 4. Tests des Mixins CBV
# =============================================================================

class DummyTestView(RoleRequiredMixin, View):
    required_roles = [UserRoleEnum.CAISSIER]

    def get(self, request, *args, **kwargs):
        return HttpResponse("OK_CAISSE")


class DummyDualRoleView(RoleRequiredMixin, View):
    required_roles = [UserRoleEnum.PROPRIETAIRE, UserRoleEnum.RESPONSABLE_PHARMACIE]
    require_all_roles = True

    def get(self, request, *args, **kwargs):
        return HttpResponse("OK_DUAL")


class DummyPharmaView(PharmacyAccessRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return HttpResponse("OK_PHARMA")


def test_role_required_mixin_unauthenticated_redirects(rf: RequestFactory) -> None:
    """Un utilisateur anonyme est redirigé vers la mire de connexion."""
    request = rf.get("/caisse/")
    request.user = AnonymousUser()

    view = DummyTestView()
    view.setup(request)
    response = view.dispatch(request)
    assert response.status_code == 302
    assert "/login/" in response.url or "login" in response.url


def test_role_required_mixin_unauthorized_raises_403(rf: RequestFactory) -> None:
    """Un utilisateur connecté sans le rôle requis reçoit une 403 (PermissionDenied)."""
    user = User.objects.create_user(
        email="accueil.only@santegeste.com",
        password="Password123!",
        is_agent_accueil=True,
    )
    request = rf.get("/caisse/")
    request.user = user

    view = DummyTestView()
    view.setup(request)
    with pytest.raises(PermissionDenied):
        view.dispatch(request)


def test_role_required_mixin_authorized_success(rf: RequestFactory) -> None:
    """Un utilisateur avec le rôle requis a accès à la vue."""
    caissier = User.objects.create_user(
        email="caissier.ok@santegeste.com",
        password="Password123!",
        is_caissier=True,
    )
    request = rf.get("/caisse/")
    request.user = caissier

    view = DummyTestView()
    view.setup(request)
    response = view.dispatch(request)
    assert response.status_code == 200
    assert response.content == b"OK_CAISSE"


def test_role_required_mixin_require_all_roles(rf: RequestFactory) -> None:
    """require_all_roles=True exige la possession conjointe de tous les rôles requis."""
    user = User.objects.create_user(
        email="proprio.single@santegeste.com",
        password="Password123!",
        is_proprietaire=True,
        is_responsable_pharmacie=False,
    )
    request = rf.get("/dual/")
    request.user = user

    view = DummyDualRoleView()
    view.setup(request)
    with pytest.raises(PermissionDenied):
        view.dispatch(request)

    # Maintenant on lui accorde aussi le 2e rôle
    user.is_responsable_pharmacie = True
    user.save()
    response = view.dispatch(request)
    assert response.status_code == 200
    assert response.content == b"OK_DUAL"


def test_pharmacy_access_mixin_allows_responsable_by_inheritance(rf: RequestFactory) -> None:
    """PharmacyAccessRequiredMixin accepte le responsable pharmacie grâce à l'héritage."""
    resp = User.objects.create_user(
        email="chef.pharma@santegeste.com",
        password="Password123!",
        is_responsable_pharmacie=True,
    )
    request = rf.get("/pharmacie/")
    request.user = resp

    view = DummyPharmaView()
    view.setup(request)
    response = view.dispatch(request)
    assert response.status_code == 200
    assert response.content == b"OK_PHARMA"


# =============================================================================
# 5. Tests des Décorateurs FBV
# =============================================================================

@role_required(UserRoleEnum.CAISSIER)
def sample_caissier_fbv(request):
    return HttpResponse("FBV_CAISSE")


@responsable_pharmacie_required
def sample_resp_fbv(request):
    return HttpResponse("FBV_RESP")


@patient_management_required
def sample_patient_fbv(request):
    return HttpResponse("FBV_PATIENTS")


@role_required(UserRoleEnum.PROPRIETAIRE, raise_exception=False, login_url="/custom-login/")
def sample_proprio_redirect_fbv(request):
    return HttpResponse("FBV_PROPRIO")


def test_role_required_decorator_denies_unauthorized(rf: RequestFactory) -> None:
    """Vérifie la levée de PermissionDenied par le décorateur."""
    user = User.objects.create_user(
        email="doctor.only@santegeste.com",
        password="Password123!",
        is_personnel_medical=True,
    )
    request = rf.get("/fbv/caisse/")
    request.user = user

    with pytest.raises(PermissionDenied):
        sample_caissier_fbv(request)


def test_role_required_decorator_allows_authorized(rf: RequestFactory) -> None:
    """Vérifie l'accès réussi avec le décorateur."""
    caissier = User.objects.create_user(
        email="caissier.fbv@santegeste.com",
        password="Password123!",
        is_caissier=True,
    )
    request = rf.get("/fbv/caisse/")
    request.user = caissier

    response = sample_caissier_fbv(request)
    assert response.status_code == 200
    assert response.content == b"FBV_CAISSE"


def test_role_required_decorator_redirects_when_raise_exception_false(rf: RequestFactory) -> None:
    """Si raise_exception=False, redirige vers l'URL indiquée."""
    user = User.objects.create_user(
        email="simple.user@santegeste.com",
        password="Password123!",
    )
    request = rf.get("/fbv/proprio/")
    request.user = user

    response = sample_proprio_redirect_fbv(request)
    assert response.status_code == 302
    assert "/custom-login/" in response.url


def test_patient_management_required_decorator(rf: RequestFactory) -> None:
    """Le décorateur autorise soit l'accueil soit le personnel médical."""
    accueil = User.objects.create_user(
        email="accueil.fbv@santegeste.com",
        password="Password123!",
        is_agent_accueil=True,
    )
    med = User.objects.create_user(
        email="med.fbv@santegeste.com",
        password="Password123!",
        is_personnel_medical=True,
    )
    other = User.objects.create_user(
        email="other.fbv@santegeste.com",
        password="Password123!",
        is_caissier=True,
    )

    req1 = rf.get("/patients/")
    req1.user = accueil
    assert sample_patient_fbv(req1).status_code == 200

    req2 = rf.get("/patients/")
    req2.user = med
    assert sample_patient_fbv(req2).status_code == 200

    req3 = rf.get("/patients/")
    req3.user = other
    with pytest.raises(PermissionDenied):
        sample_patient_fbv(req3)


# =============================================================================
# 6. Tests des Gabarits et Template Tags
# =============================================================================

def test_template_tags_has_role() -> None:
    """Teste le filtre has_role."""
    user = User.objects.create_user(
        email="proprio.tpl@santegeste.com",
        password="Password123!",
        is_proprietaire=True,
    )
    tpl = Template(
        "{% load rbac_tags %}"
        "{% if user|has_role:'proprietaire' %}OUI{% else %}NON{% endif %}"
    )
    rendered = tpl.render(Context({"user": user}))
    assert rendered == "OUI"

    rendered_false = tpl.render(Context({"user": AnonymousUser()}))
    assert rendered_false == "NON"


def test_template_tags_has_any_role() -> None:
    """Teste le filtre has_any_role avec chaîne séparée par des virgules."""
    med = User.objects.create_user(
        email="med.tpl@santegeste.com",
        password="Password123!",
        is_personnel_medical=True,
    )
    tpl = Template(
        "{% load rbac_tags %}"
        "{% if user|has_any_role:'agent_accueil,personnel_medical' %}ACCES_OK{% else %}REFUS{% endif %}"
    )
    assert tpl.render(Context({"user": med})) == "ACCES_OK"

    stranger = User.objects.create_user(
        email="stranger.tpl@santegeste.com",
        password="Password123!",
    )
    assert tpl.render(Context({"user": stranger})) == "REFUS"


def test_template_tags_has_all_roles() -> None:
    """Teste le filtre has_all_roles."""
    resp = User.objects.create_user(
        email="resp.tpl@santegeste.com",
        password="Password123!",
        is_responsable_pharmacie=True,
    )
    tpl = Template(
        "{% load rbac_tags %}"
        "{% if user|has_all_roles:'responsable_pharmacie,vendeur_pharmacie' %}HERITAGE_OK{% else %}NON{% endif %}"
    )
    assert tpl.render(Context({"user": resp})) == "HERITAGE_OK"


def test_template_simple_tags_user_has_role() -> None:
    """Teste le tag simple user_has_role."""
    user = User.objects.create_user(
        email="caissier.tag@santegeste.com",
        password="Password123!",
        is_caissier=True,
    )
    tpl = Template(
        "{% load rbac_tags %}"
        "{% user_has_role user 'caissier' 'proprietaire' as can_access %}"
        "Result:{{ can_access }}"
    )
    assert tpl.render(Context({"user": user})) == "Result:True"


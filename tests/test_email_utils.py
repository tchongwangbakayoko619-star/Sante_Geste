"""Tests unitaires pour le module d'e-mails (utils/email.py)."""

from django.core import mail

from utils.email import (
    get_base_url,
    send_otp_email_helper,
    send_security_alert_email_helper,
    send_transactional_email,
    send_welcome_email_helper,
)


def test_get_base_url_resolution(settings) -> None:
    """Vérifie la résolution robuste de l'URL de base avec fallbacks et variables de configuration."""
    settings.DOMAIN_NAME = "app.santegeste.com"
    settings.DEBUG = False
    assert get_base_url() == "https://app.santegeste.com"

    settings.DOMAIN_NAME = None
    settings.DEBUG = True
    assert "http://" in get_base_url()



def test_send_transactional_email_plain_text() -> None:
    """Vérifie l'envoi d'un e-mail transactionnel en texte brut."""
    success = send_transactional_email(
        subject="Test Sujet",
        recipient_list=["test@santegeste.com"],
        message_text="Ceci est un test en texte brut.",
    )
    assert success is True
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "Test Sujet"
    assert mail.outbox[0].to == ["test@santegeste.com"]


def test_send_otp_email_helper() -> None:
    """Vérifie le helper d'envoi d'OTP."""
    success = send_otp_email_helper(
        recipient_email="otp-test@santegeste.com",
        user_name="Alice",
        raw_code="654321",
        purpose_label="vérification",
    )
    assert success is True
    assert len(mail.outbox) == 1
    assert "654321" in mail.outbox[0].subject


def test_send_welcome_email_helper() -> None:
    """Vérifie le helper d'e-mail de bienvenue."""
    success = send_welcome_email_helper(
        recipient_email="welcome-test@santegeste.com",
        user_name="Bob",
    )
    assert success is True
    assert len(mail.outbox) == 1
    assert "Bienvenue" in mail.outbox[0].subject


def test_send_security_alert_email_helper() -> None:
    """Vérifie le helper d'alerte de sécurité."""
    success = send_security_alert_email_helper(
        recipient_email="security-test@santegeste.com",
        user_name="Charlie",
        action_label="Modification du mot de passe",
    )
    assert success is True
    assert len(mail.outbox) == 1
    assert "Alerte de sécurité" in mail.outbox[0].subject

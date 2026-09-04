"""Tests unitaires pour les tâches d'arrière-plan Celery (apps/users/tasks.py)."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone

from apps.users.models import OTP
from apps.users.tasks import (
    cleanup_expired_otps_task,
    send_otp_email_task,
    send_password_changed_notification_task,
    send_welcome_email_task,
)
from utils.enums import OTPPurposeEnum

User = get_user_model()


@pytest.mark.django_db
def test_send_otp_email_task_success() -> None:
    """Vérifie l'envoi asynchrone réussi d'un e-mail OTP."""
    user = User.objects.create_user(
        email="task-otp@santegeste.com",
        password="ValidPassword123!",
        first_name="Paul",
    )

    result = send_otp_email_task.apply(
        args=[str(user.id), "123456", OTPPurposeEnum.REGISTRATION]
    ).get()
    assert result is True
    assert len(mail.outbox) == 1
    assert "123456" in mail.outbox[0].subject
    assert "task-otp@santegeste.com" in mail.outbox[0].to


@pytest.mark.django_db
def test_send_welcome_email_task_success() -> None:
    """Vérifie l'envoi de l'e-mail de bienvenue."""
    user = User.objects.create_user(
        email="welcome@santegeste.com",
        password="ValidPassword123!",
    )

    result = send_welcome_email_task.apply(args=[str(user.id)]).get()
    assert result is True
    assert len(mail.outbox) == 1
    assert "Bienvenue" in mail.outbox[0].subject


@pytest.mark.django_db
def test_send_password_changed_notification_task_success() -> None:
    """Vérifie l'envoi de l'alerte de mot de passe modifié."""
    user = User.objects.create_user(
        email="security@santegeste.com",
        password="ValidPassword123!",
    )

    result = send_password_changed_notification_task.apply(args=[str(user.id)]).get()
    assert result is True
    assert len(mail.outbox) == 1
    assert "Alerte de sécurité" in mail.outbox[0].subject


@pytest.mark.django_db
def test_cleanup_expired_otps_task() -> None:
    """Vérifie la suppression automatique des enregistrements OTP expirés et consommés."""
    user = User.objects.create_user(
        email="cleanup@santegeste.com",
        password="ValidPassword123!",
    )

    # 1. OTP actif (ne doit pas être supprimé)
    OTP.objects.create(
        user=user,
        code_hash="active_hash",
        purpose=OTPPurposeEnum.REGISTRATION,
        expires_at=timezone.now() + timezone.timedelta(minutes=10),
    )

    # 2. OTP expiré (doit être supprimé)
    OTP.objects.create(
        user=user,
        code_hash="expired_hash",
        purpose=OTPPurposeEnum.REGISTRATION,
        expires_at=timezone.now() - timezone.timedelta(minutes=10),
    )

    # 3. OTP utilisé (doit être supprimé)
    OTP.objects.create(
        user=user,
        code_hash="consumed_hash",
        purpose=OTPPurposeEnum.REGISTRATION,
        expires_at=timezone.now() + timezone.timedelta(minutes=10),
        is_used=True,
    )

    deleted_count = cleanup_expired_otps_task.apply().get()
    assert deleted_count == 2
    assert OTP.objects.filter(user=user).count() == 1

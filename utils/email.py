"""Utilitaires d'envoi d'e-mails transactionnels et notifications pour SantéGeste."""

from __future__ import annotations

import logging
from typing import Any, Sequence

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def send_transactional_email(
    subject: str,
    recipient_list: Sequence[str],
    message_text: str = "",
    html_template: str | None = None,
    context: dict[str, Any] | None = None,
    from_email: str | None = None,
) -> bool:
    """Envoie un e-mail transactionnel avec support du format texte et HTML.

    Args:
        subject (str): Sujet de l'e-mail.
        recipient_list (Sequence[str]): Liste des adresses destinataires.
        message_text (str): Contenu au format texte brut.
        html_template (str | None): Chemin du template HTML (optionnel).
        context (dict[str, Any] | None): Variables de contexte pour le template.
        from_email (str | None): Adresse d'expédition (par défaut settings.DEFAULT_FROM_EMAIL).

    Returns:
        bool: True si l'envoi a réussi, False sinon.
    """
    sender = from_email or settings.DEFAULT_FROM_EMAIL
    context = context or {}

    if html_template:
        try:
            html_content = render_to_string(html_template, context)
            msg = EmailMultiAlternatives(
                subject=subject,
                body=message_text,
                from_email=sender,
                to=list(recipient_list),
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            logger.info("E-mail HTML envoyé avec succès à %s.", recipient_list)
            return True
        except Exception as exc:
            logger.error("Erreur lors de l'envoi de l'e-mail HTML à %s: %s", recipient_list, exc)
            raise

    try:
        send_mail(
            subject=subject,
            message=message_text,
            from_email=sender,
            recipient_list=list(recipient_list),
            fail_silently=False,
        )
        logger.info("E-mail texte envoyé avec succès à %s.", recipient_list)
        return True
    except Exception as exc:
        logger.error("Erreur lors de l'envoi de l'e-mail texte à %s: %s", recipient_list, exc)
        raise


def get_base_url() -> str:
    """Détermine l'URL de base absolue de l'application de manière ultra-robuste.

    Priorités :
    1. settings.BASE_URL ou settings.DOMAIN_NAME si configuré.
    2. Framework Django Sites (Site.objects.get_current()).
    3. Fallback sécurisé selon settings.DEBUG (http://localhost:8000 vs https://santegeste.com).
    """
    custom_domain = getattr(settings, "DOMAIN_NAME", None) or getattr(settings, "BASE_URL", None)
    if custom_domain:
        if custom_domain.startswith(("http://", "https://")):
            return custom_domain.rstrip("/")
        scheme = "http" if settings.DEBUG else "https"
        return f"{scheme}://{custom_domain.rstrip('/')}"

    try:
        from django.contrib.sites.models import Site

        current_site = Site.objects.get_current()
        domain = current_site.domain
        if domain and domain != "example.com":
            scheme = "http" if settings.DEBUG else "https"
            return f"{scheme}://{domain}"
    except Exception:
        pass

    scheme = "http" if settings.DEBUG else "https"
    default_host = "localhost:8000" if settings.DEBUG else "santegeste.com"
    return f"{scheme}://{default_host}"


def send_otp_email_helper(
    recipient_email: str,
    user_name: str,
    raw_code: str,
    purpose: str = "registration",
    purpose_label: str | None = None,
    token: str = "",
) -> bool:
    """Helper d'envoi d'un code OTP à un utilisateur avec rendu HTML adapté (inscription, réinitialisation de mot de passe)."""
    from utils.enums import OTPPurposeEnum

    target_purpose = purpose or purpose_label or "registration"

    if target_purpose in (OTPPurposeEnum.PASSWORD_RESET, "password_reset", "réinitialisation"):
        p_label = str(_("réinitialisation de votre mot de passe"))
        p_title = str(_("Réinitialisation de mot de passe"))
        subject = str(
            _("Réinitialisation de votre mot de passe SantéGeste - Code : %(code)s")
            % {"code": raw_code}
        )
    else:
        p_label = str(_("validation d'inscription"))
        p_title = str(_("Validation d'inscription"))
        subject = str(
            _("Code de validation de votre compte SantéGeste - %(code)s")
            % {"code": raw_code}
        )

    from django.urls import reverse

    base_url = get_base_url()

    if target_purpose in (OTPPurposeEnum.PASSWORD_RESET, "password_reset", "réinitialisation"):
        action_path = reverse("users:password-reset-verify-otp")
    else:
        action_path = reverse("users:otp-verify")

    action_url = f"{base_url}{action_path}"
    if token:
        action_url = f"{action_url}?token={token}"

    validity_minutes = int(getattr(settings, "OTP_VALID_MINUTES", 10))

    message_text = str(
        _(
            "Bonjour %(name)s,\n\n"
            "Vous avez demandé un code pour la %(purpose)s de votre compte SantéGeste.\n"
            "Voici votre code de sécurité : %(code)s.\n"
            "Accédez directement à la page de vérification : %(url)s\n"
            "Ce code expire dans %(minutes)d minutes.\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, veuillez ignorer ce message.\n\n"
            "L'équipe SantéGeste."
        )
        % {
            "name": user_name,
            "purpose": p_label,
            "code": raw_code,
            "url": action_url,
            "minutes": validity_minutes,
        }
    )
    context = {
        "user_name": user_name,
        "raw_code": raw_code,
        "purpose_label": p_label,
        "purpose_title": p_title,
        "action_url": action_url,
        "validity_minutes": validity_minutes,
    }

    return send_transactional_email(
        subject=subject,
        recipient_list=[recipient_email],
        message_text=message_text,
        html_template="emails/otp_email.html",
        context=context,
    )





def send_welcome_email_helper(recipient_email: str, user_name: str) -> bool:
    """Helper d'envoi de l'e-mail de bienvenue post-activation avec rendu HTML."""
    subject = str(_("Bienvenue sur SantéGeste !"))
    message_text = str(
        _(
            "Bonjour %(name)s,\n\n"
            "Votre compte SantéGeste a été activé avec succès.\n"
            "Vous pouvez désormais vous connecter et utiliser l'ensemble des fonctionnalités de la plateforme.\n\n"
            "Cordialement,\n"
            "L'équipe SantéGeste."
        )
        % {"name": user_name}
    )
    context = {
        "user_name": user_name,
        "login_url": "/users/login/",
    }
    return send_transactional_email(
        subject=subject,
        recipient_list=[recipient_email],
        message_text=message_text,
        html_template="emails/welcome_email.html",
        context=context,
    )


def send_security_alert_email_helper(
    recipient_email: str,
    user_name: str,
    action_label: str = "Modification du mot de passe",
) -> bool:
    """Helper d'envoi d'une alerte de sécurité avec rendu HTML."""
    subject = str(_("Alerte de sécurité SantéGeste : %(action)s") % {"action": action_label})
    message_text = str(
        _(
            "Bonjour %(name)s,\n\n"
            "Une opération sensible (%(action)s) a été effectuée sur votre compte SantéGeste.\n"
            "Si vous n'avez pas réalisé cette action, contactez immédiatement le support technique.\n\n"
            "L'équipe SantéGeste."
        )
        % {"name": user_name, "action": action_label}
    )
    context = {
        "user_name": user_name,
        "action_label": action_label,
    }
    return send_transactional_email(
        subject=subject,
        recipient_list=[recipient_email],
        message_text=message_text,
        html_template="emails/security_alert_email.html",
        context=context,
    )


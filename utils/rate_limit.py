"""Utilitaires de limitation de débit (Rate Limiting) et anti-brute-force."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from django.core.cache import cache

if TYPE_CHECKING:
    from django.http import HttpRequest

# Paramètres par défaut configurables via settings
DEFAULT_LOGIN_MAX_ATTEMPTS = 5
DEFAULT_LOGIN_LOCKOUT_SECONDS = 900  # 15 minutes


def get_client_ip(request: HttpRequest) -> str:
    """Extrait l'adresse IP du client (support proxy inverse)."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "")
    return ip or "127.0.0.1"


def _build_rate_limit_keys(ip: str, email: str = "") -> list[str]:
    """Génère les clés de cache de verrouillage pour l'IP et pour le couple IP+Email."""
    keys = []
    ip_hash = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]
    keys.append(f"login_rate_limit:ip:{ip_hash}")

    if email:
        clean_email = email.strip().lower()
        combined = f"{ip}:{clean_email}"
        combined_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
        keys.append(f"login_rate_limit:account:{combined_hash}")

    return keys


def check_login_rate_limit(request: HttpRequest, email: str = "") -> tuple[bool, int]:
    """Vérifie si l'adresse IP ou le couple IP/email est actuellement bloqué.

    Returns:
        tuple[bool, int]: (est_bloqué, secondes_restantes)
    """
    max_attempts = getattr(
        settings, "AUTH_LOGIN_MAX_ATTEMPTS", DEFAULT_LOGIN_MAX_ATTEMPTS
    )
    lockout_duration = getattr(
        settings, "AUTH_LOGIN_LOCKOUT_SECONDS", DEFAULT_LOGIN_LOCKOUT_SECONDS
    )
    ip = get_client_ip(request)
    keys = _build_rate_limit_keys(ip, email)

    for key in keys:
        attempts = cache.get(key)
        if attempts is not None and attempts >= max_attempts:
            remaining: Any = cache.ttl(key) if hasattr(cache, "ttl") else None
            if remaining is not None and remaining > 0:
                return True, int(remaining)
            return True, lockout_duration

    return False, 0


def record_failed_login(request: HttpRequest, email: str = "") -> int:
    """Incrémente le compteur d'échecs de connexion pour l'IP et le couple IP/email.

    Returns:
        int: Nombre maximum d'échecs enregistrés.
    """
    lockout_duration = getattr(
        settings, "AUTH_LOGIN_LOCKOUT_SECONDS", DEFAULT_LOGIN_LOCKOUT_SECONDS
    )
    ip = get_client_ip(request)
    keys = _build_rate_limit_keys(ip, email)
    highest_count = 1

    for key in keys:
        try:
            # Si la clé existe, incr() incrémente de façon atomique
            new_count = cache.incr(key)
        except (ValueError, KeyError):
            # Clé inexistante dans le cache, on initialise avec timeout
            cache.set(key, 1, timeout=lockout_duration)
            new_count = 1

        highest_count = max(highest_count, new_count)

    return highest_count


def reset_login_rate_limit(request: HttpRequest, email: str = "") -> None:
    """Réinitialise les compteurs d'échec après une authentification réussie."""
    ip = get_client_ip(request)
    keys = _build_rate_limit_keys(ip, email)
    for key in keys:
        cache.delete(key)

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

    Précision garantie à la seconde près sur n'importe quel backend de cache
    (Redis, LocMemCache, etc.) sans dépendre de cache.ttl().

    Returns:
        tuple[bool, int]: (est_bloqué, secondes_restantes)
    """
    import math
    import time

    now = time.time()
    ip = get_client_ip(request)
    keys = _build_rate_limit_keys(ip, email)

    for key in keys:
        record = cache.get(key)
        if record and isinstance(record, dict):
            blocked_until = record.get("blocked_until", 0)
            if blocked_until > now:
                remaining = int(math.ceil(blocked_until - now))
                return True, max(1, remaining)
        elif isinstance(record, int):
            max_attempts = getattr(
                settings, "AUTH_LOGIN_MAX_ATTEMPTS", DEFAULT_LOGIN_MAX_ATTEMPTS
            )
            lockout_duration = getattr(
                settings, "AUTH_LOGIN_LOCKOUT_SECONDS", DEFAULT_LOGIN_LOCKOUT_SECONDS
            )
            if record >= max_attempts:
                return True, lockout_duration

    return False, 0


def record_failed_login(request: HttpRequest, email: str = "") -> int:
    """Incrémente le compteur d'échecs avec horodatage pour une précision TTL absolue.

    Returns:
        int: Nombre maximum d'échecs enregistrés.
    """
    import time

    max_attempts = getattr(
        settings, "AUTH_LOGIN_MAX_ATTEMPTS", DEFAULT_LOGIN_MAX_ATTEMPTS
    )
    lockout_duration = getattr(
        settings, "AUTH_LOGIN_LOCKOUT_SECONDS", DEFAULT_LOGIN_LOCKOUT_SECONDS
    )
    now = time.time()
    ip = get_client_ip(request)
    keys = _build_rate_limit_keys(ip, email)
    highest_count = 1

    for key in keys:
        record = cache.get(key)
        if record and isinstance(record, dict):
            attempts = record.get("attempts", 0) + 1
            first_attempt = record.get("first_attempt", now)
            if now - first_attempt > lockout_duration:
                attempts = 1
                first_attempt = now
            blocked_until = (
                now + lockout_duration if attempts >= max_attempts else 0
            )
            new_record = {
                "attempts": attempts,
                "first_attempt": first_attempt,
                "blocked_until": blocked_until,
            }
        else:
            attempts = 1
            new_record = {
                "attempts": 1,
                "first_attempt": now,
                "blocked_until": now + lockout_duration if 1 >= max_attempts else 0,
            }

        cache.set(key, new_record, timeout=lockout_duration)
        highest_count = max(highest_count, attempts)

    return highest_count


def reset_login_rate_limit(request: HttpRequest, email: str = "") -> None:
    """Réinitialise les compteurs d'échec après une authentification réussie."""
    ip = get_client_ip(request)
    keys = _build_rate_limit_keys(ip, email)
    for key in keys:
        cache.delete(key)

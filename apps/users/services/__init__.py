"""Services du module d'utilisateurs SantéGeste."""

from apps.users.services.otp import (
    OtpCooldownError,
    request_otp,
    verify_otp_by_token,
    verify_otp_by_user,
)
from apps.users.services.password import (
    PasswordResetError,
    confirm_password_reset,
    request_password_reset,
    verify_password_reset_otp,
)
from apps.users.services.profile import (
    update_medical_profile,
    update_user_profile,
)
from apps.users.services.rbac import (
    ROLE_FIELD_MAP,
    ROLE_INHERITANCE,
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
from apps.users.services.registration import (
    confirm_registration_otp,
    register_user,
)

__all__ = [
    "OtpCooldownError",
    "PasswordResetError",
    "ROLE_FIELD_MAP",
    "ROLE_INHERITANCE",
    "can_manage_cash",
    "can_manage_patients",
    "can_manage_pharmacy",
    "can_prescribe",
    "can_sell_pharmacy",
    "can_validate_sensitive_ops",
    "check_user_roles",
    "confirm_password_reset",
    "confirm_registration_otp",
    "get_direct_roles",
    "get_effective_roles",
    "has_all_roles",
    "has_role",
    "normalize_role",
    "register_user",
    "request_otp",
    "request_password_reset",
    "update_medical_profile",
    "update_user_profile",
    "verify_otp_by_token",
    "verify_otp_by_user",
    "verify_password_reset_otp",
]

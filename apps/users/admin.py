"""Admin panel registration for users application."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.users.forms import UserAdminChangeForm, UserAdminCreationForm
from apps.users.models import OTP, MedicalProfile, User


class MedicalProfileInline(admin.StackedInline):
    """Inline configuration for MedicalProfile in UserAdmin."""

    model = MedicalProfile
    can_delete = False
    verbose_name_plural = "Profil Médical"
    fk_name = "user"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for User model."""

    add_form = UserAdminCreationForm
    form = UserAdminChangeForm
    inlines = [MedicalProfileInline]
    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_verified",
        "is_personnel_medical",
        "is_proprietaire",
        "is_caissier",
        "is_responsable_pharmacie",
        "is_vendeur_pharmacie",
        "is_agent_accueil",
    )
    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
        "is_verified",
        "is_personnel_medical",
        "is_proprietaire",
        "is_caissier",
        "is_responsable_pharmacie",
        "is_vendeur_pharmacie",
        "is_agent_accueil",
    )
    search_fields = ("email", "first_name", "last_name", "telephone")
    ordering = ("email",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "last_login",
        "created_by",
        "updated_by",
    )

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Informations personnelles"),
            {"fields": ("first_name", "last_name", "telephone", "avatar")},
        ),
        (
            _("Rôles applicatifs (RBAC)"),
            {
                "fields": (
                    "is_proprietaire",
                    "is_personnel_medical",
                    "is_responsable_pharmacie",
                    "is_vendeur_pharmacie",
                    "is_caissier",
                    "is_agent_accueil",
                )
            },
        ),
        (
            _("Statut et permissions"),
            {
                "fields": (
                    "is_active",
                    "is_verified",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            _("Traçabilité et dates"),
            {
                "fields": (
                    "last_login",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "updated_by",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            _("Identifiants & Connexion"),
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                ),
            },
        ),
        (
            _("Informations personnelles"),
            {
                "classes": ("wide",),
                "fields": (
                    "first_name",
                    "last_name",
                    "telephone",
                    "avatar",
                ),
            },
        ),
        (
            _("Attribution du rôle (RBAC)"),
            {
                "classes": ("wide",),
                "fields": (
                    "is_proprietaire",
                    "is_personnel_medical",
                    "is_responsable_pharmacie",
                    "is_vendeur_pharmacie",
                    "is_caissier",
                    "is_agent_accueil",
                ),
            },
        ),
        (
            _("Statut et permissions système"),
            {
                "classes": ("wide",),
                "fields": (
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )


@admin.register(MedicalProfile)
class MedicalProfileAdmin(admin.ModelAdmin):
    """Admin configuration for MedicalProfile model."""

    list_display = ("user", "specialite", "numero_ordre")
    search_fields = ("user__email", "specialite", "numero_ordre")


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    """Configuration Admin en lecture seule pour l'audit des codes OTP."""

    list_display = (
        "user",
        "purpose",
        "is_used",
        "attempts",
        "expires_at",
        "used_at",
        "created_at",
    )
    list_filter = ("purpose", "is_used", "created_at")
    search_fields = ("user__email", "code_hash")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "user",
        "code_hash",
        "purpose",
        "expires_at",
        "is_used",
        "used_at",
        "attempts",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: Any | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: Any | None = None
    ) -> bool:
        return True



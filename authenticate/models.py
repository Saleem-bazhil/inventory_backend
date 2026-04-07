from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    # Legacy roles (kept for backward compat during migration)
    SUPER_ADMIN = "super_admin"
    SUB_ADMIN = "sub_admin"

    # New workflow roles
    ADMIN = "admin"
    MANAGER = "manager"
    ENGINEER = "engineer"
    RECEPTIONIST = "receptionist"
    CC_TEAM = "cc_team"

    ROLE_CHOICES = (
        (ADMIN, "Admin"),
        (MANAGER, "Manager"),
        (ENGINEER, "Engineer"),
        (RECEPTIONIST, "Receptionist"),
        (CC_TEAM, "CC Team"),
        # Legacy (will be migrated)
        (SUPER_ADMIN, "Super Admin"),
        (SUB_ADMIN, "Sub Admin"),
    )

    # Regions
    VELLORE = "vellore"
    SALEM = "salem"
    CHENNAI = "chennai"
    KANCHIPURAM = "kanchipuram"
    HOSUR = "hosur"
    REGION_CHOICES = (
        (VELLORE, "Vellore"),
        (SALEM, "Salem"),
        (CHENNAI, "Chennai"),
        (KANCHIPURAM, "Kanchipuram"),
        (HOSUR, "Hosur"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ENGINEER)
    region = models.CharField(
        max_length=20, choices=REGION_CHOICES, blank=True, null=True,
        help_text="Required for non-admin roles.",
    )

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_super_admin(self):
        return self.role in (self.SUPER_ADMIN, self.ADMIN)

    @property
    def is_admin(self):
        return self.role in (self.SUPER_ADMIN, self.ADMIN)

    @property
    def effective_role(self):
        """Map legacy roles to new workflow roles."""
        mapping = {
            self.SUPER_ADMIN: self.ADMIN,
            self.SUB_ADMIN: self.ENGINEER,
        }
        return mapping.get(self.role, self.role)

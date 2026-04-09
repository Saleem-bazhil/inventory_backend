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
        """Map legacy roles to new workflow roles.

        sub_admin = regional admin with full control within their region,
        NOT a field engineer. They manage engineers, assign tickets, etc.
        """
        mapping = {
            self.SUPER_ADMIN: self.ADMIN,
            self.SUB_ADMIN: self.ADMIN,
        }
        return mapping.get(self.role, self.role)


class Engineer(models.Model):
    """
    Separate engineer entity — field technicians managed by sub-admins.
    Engineers are assigned to service tickets but do not log into the system.
    """

    STATUS_CHOICES = (
        ("active", "Active"),
        ("inactive", "Inactive"),
    )

    REGION_CHOICES = UserProfile.REGION_CHOICES

    name = models.CharField(max_length=255, verbose_name="Full Name")
    email = models.EmailField(blank=True, default="", verbose_name="Email")
    phone = models.CharField(max_length=20, blank=True, default="", verbose_name="Phone")
    region = models.CharField(
        max_length=20, choices=REGION_CHOICES,
        verbose_name="Region",
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default="active",
        verbose_name="Status",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_engineers", verbose_name="Created By",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Engineer"
        verbose_name_plural = "Engineers"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_region_display()})"

from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    # Roles
    SUPER_ADMIN = "super_admin"
    SUB_ADMIN = "sub_admin"
    ROLE_CHOICES = (
        (SUPER_ADMIN, "Super Admin"),
        (SUB_ADMIN, "Sub Admin"),
    )

    # Regions
    VELLORE = "vellore"
    SALEM = "salem"
    CHENNAI = "chennai"
    KANCHIPURAM = "kanchipuram"
    REGION_CHOICES = (
        (VELLORE, "Vellore"),
        (SALEM, "Salem"),
        (CHENNAI, "Chennai"),
        (KANCHIPURAM, "Kanchipuram"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=SUB_ADMIN)
    region = models.CharField(
        max_length=20, choices=REGION_CHOICES, blank=True, null=True,
        help_text="Required for sub_admin. Super admin can access all regions.",
    )

    def __str__(self):
        if self.role == self.SUPER_ADMIN:
            return f"{self.user.username} (Super Admin)"
        return f"{self.user.username} ({self.get_region_display()})"

    @property
    def is_super_admin(self):
        return self.role == self.SUPER_ADMIN

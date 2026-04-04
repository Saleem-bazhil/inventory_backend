from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    ADMIN = "admin"
    EMPLOYEE = "employee"
    ROLE_CHOICES = (
        (ADMIN, "Admin"),
        (EMPLOYEE, "Employee"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=EMPLOYEE)

    def __str__(self):
        return self.user.username
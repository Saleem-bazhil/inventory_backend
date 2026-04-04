from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    default_role = UserProfile.ADMIN if instance.is_staff or instance.is_superuser else UserProfile.EMPLOYEE

    if created:
        UserProfile.objects.create(user=instance, role=default_role)
        return

    profile, _ = UserProfile.objects.get_or_create(user=instance)
    if instance.is_staff or instance.is_superuser:
        if profile.role != UserProfile.ADMIN:
            profile.role = UserProfile.ADMIN
            profile.save(update_fields=["role"])
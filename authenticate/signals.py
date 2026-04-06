from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    default_role = UserProfile.SUPER_ADMIN if instance.is_superuser else UserProfile.SUB_ADMIN

    if created:
        UserProfile.objects.create(user=instance, role=default_role)
        return

    profile, _ = UserProfile.objects.get_or_create(user=instance)
    if instance.is_superuser and profile.role != UserProfile.SUPER_ADMIN:
        profile.role = UserProfile.SUPER_ADMIN
        profile.save(update_fields=["role"])

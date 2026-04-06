from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from unfold.admin import ModelAdmin, StackedInline

from .models import UserProfile


class UserProfileInline(StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Profile"
    fields = ("role", "region")


admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    inlines = [UserProfileInline]
    list_display = ("username", "email", "get_role", "get_region", "is_staff", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name")
    list_filter = ("is_staff", "is_superuser", "is_active", "userprofile__role", "userprofile__region")
    list_filter_submit = True

    @admin.display(description="Role")
    def get_role(self, obj):
        profile = getattr(obj, "userprofile", None)
        return profile.get_role_display() if profile else "-"

    @admin.display(description="Region")
    def get_region(self, obj):
        profile = getattr(obj, "userprofile", None)
        return profile.get_region_display() if profile and profile.region else "-"


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

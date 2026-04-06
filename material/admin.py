from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import MaterialTrack


@admin.register(MaterialTrack)
class MaterialTrackAdmin(ModelAdmin):
    list_display = (
        "case_id",
        "cust_name",
        "product_name",
        "service_type",
        "call_status",
        "region",
        "user",
        "arrival_date",
        "delivery_date",
    )
    search_fields = ("case_id", "cust_name", "cust_contact", "product_name", "part_number", "serial_number")
    list_filter = ("service_type", "call_status", "region", "user")
    list_filter_submit = True

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        profile = getattr(request.user, "userprofile", None)
        if profile and profile.region:
            return queryset.filter(region=profile.region)
        return queryset.filter(user=request.user)

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def save_model(self, request, obj, form, change):
        if not change:
            obj.user = request.user
            profile = getattr(request.user, "userprofile", None)
            if profile and profile.region:
                obj.region = profile.region
        super().save_model(request, obj, form, change)

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if request.user.is_superuser:
            return fields
        return [f for f in fields if f not in ("user", "region")]

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return ()
        return ("user", "region")

    def has_view_permission(self, request, obj=None):
        if not (request.user.is_active and request.user.is_staff):
            return False
        if obj is None or request.user.is_superuser:
            return True
        profile = getattr(request.user, "userprofile", None)
        if profile and profile.region:
            return obj.region == profile.region
        return obj.user_id == request.user.id

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

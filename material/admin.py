from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import MaterialTrack


@admin.register(MaterialTrack)
class MaterialTrackAdmin(ModelAdmin):
    list_display = (
        "case_id",
        "cust_name",
        "product",
        "part_number",
        "qty",
        "user",
        "in_date",
        "out_date",
    )
    search_fields = ("case_id", "cust_name", "cust_contact", "product", "part_number")
    list_filter = ("warranty", "used_part", "user", "in_date", "out_date")
    list_filter_submit = True

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(user=request.user)

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return request.user.is_active and request.user.is_staff

    def save_model(self, request, obj, form, change):
        # Sub-admins always own the records they create or update.
        if request.user.is_superuser:
            if not obj.user:
                obj.user = request.user
        else:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if request.user.is_superuser:
            return fields
        return [field for field in fields if field != "user"]

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return ()
        return ("user",)

    def has_view_permission(self, request, obj=None):
        if not (request.user.is_active and request.user.is_staff):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return obj.user_id == request.user.id

    def has_change_permission(self, request, obj=None):
        if not (request.user.is_active and request.user.is_staff):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return obj.user_id == request.user.id

    def has_delete_permission(self, request, obj=None):
        if not (request.user.is_active and request.user.is_staff):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return obj.user_id == request.user.id

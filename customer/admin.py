from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(ModelAdmin):
    list_display = ["name", "email", "phone", "company", "created_at"]
    list_filter = ["company"]
    search_fields = ["name", "email", "phone", "company"]
    readonly_fields = ["created_at", "updated_at"]

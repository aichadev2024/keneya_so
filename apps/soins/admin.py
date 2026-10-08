from django.contrib import admin

from .models import Soin


@admin.register(Soin)
class SoinAdmin(admin.ModelAdmin):
    list_display = ("reference", "patient", "type_soin", "date_soin", "soignant")
    list_filter = ("type_soin",)
    search_fields = ("reference", "patient__nom", "patient__prenom")

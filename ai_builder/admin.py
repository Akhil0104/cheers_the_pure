from django.contrib import admin

from .models import CreatedWebsite, WebsiteRevision


@admin.register(CreatedWebsite)
class CreatedWebsiteAdmin(admin.ModelAdmin):
    list_display = ("site_name", "slug", "owner", "is_published", "updated_at")
    list_filter = ("is_published", "schema_version")
    search_fields = ("site_name", "slug", "brand_name", "owner__email")
    readonly_fields = ("site_id", "created_at", "updated_at")


@admin.register(WebsiteRevision)
class WebsiteRevisionAdmin(admin.ModelAdmin):
    list_display = ("site", "revision_number", "action", "created_by", "created_at")
    list_filter = ("action", "schema_version")
    search_fields = ("site__site_name", "site__slug", "created_by__email")
    readonly_fields = ("revision_id", "created_at")

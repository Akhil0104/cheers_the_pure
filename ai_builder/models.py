import uuid

from django.conf import settings
from django.db import models


class CreatedWebsite(models.Model):
    site_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_websites",
    )
    prompt = models.TextField()
    site_name = models.CharField(max_length=120)
    brand_name = models.CharField(max_length=120)
    theme = models.CharField(max_length=16)
    schema_json = models.JSONField()
    is_published = models.BooleanField(default=False)
    share_token = models.UUIDField(null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.site_name} ({self.site_id})"
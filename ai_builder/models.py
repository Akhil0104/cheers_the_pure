import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


class CreatedWebsite(models.Model):
    site_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_websites",
    )
    prompt = models.TextField()
    site_name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    brand_name = models.CharField(max_length=120)
    theme = models.CharField(max_length=16)
    schema_version = models.CharField(max_length=16, default="1.0")
    schema_json = models.JSONField()
    is_published = models.BooleanField(default=False)
    share_token = models.UUIDField(null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.site_name)[:140] or "website"
            self.slug = f"{base}-{uuid.uuid4().hex[:12]}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.site_name} ({self.site_id})"


class WebsiteRevision(models.Model):
    class Action(models.TextChoices):
        GENERATED = "generated", "Generated"
        INLINE_EDIT = "inline_edit", "Inline edit"
        SECTION_REFINE = "section_refine", "Section refinement"
        IMPORTED = "imported", "Imported"
        RESTORED = "restored", "Restored"

    revision_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(
        CreatedWebsite,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    revision_number = models.PositiveIntegerField()
    schema_version = models.CharField(max_length=16)
    schema_json = models.JSONField()
    action = models.CharField(max_length=24, choices=Action.choices)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="website_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["site", "revision_number"],
                name="unique_website_revision_number",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Website revisions are immutable.")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.site.site_name} revision {self.revision_number}"
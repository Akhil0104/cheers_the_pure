from django.db import migrations, models
import django.db.models.deletion
import uuid


def populate_website_persistence(apps, schema_editor):
    CreatedWebsite = apps.get_model("ai_builder", "CreatedWebsite")
    WebsiteRevision = apps.get_model("ai_builder", "WebsiteRevision")
    for site in CreatedWebsite.objects.all().iterator():
        site.slug = f"website-{site.site_id.hex[:12]}"
        site.schema_version = site.schema_json.get("schema_version", "1.0")
        site.save(update_fields=["slug", "schema_version"])
        WebsiteRevision.objects.create(
            site=site,
            revision_number=1,
            schema_version=site.schema_version,
            schema_json=site.schema_json,
            action="generated",
            metadata={"source": "migration_backfill"},
            created_by=site.owner,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("ai_builder", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="createdwebsite",
            name="schema_version",
            field=models.CharField(default="1.0", max_length=16),
        ),
        migrations.AddField(
            model_name="createdwebsite",
            name="slug",
            field=models.SlugField(blank=True, max_length=160, null=True, unique=True),
        ),
        migrations.CreateModel(
            name="WebsiteRevision",
            fields=[
                ("revision_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("revision_number", models.PositiveIntegerField()),
                ("schema_version", models.CharField(max_length=16)),
                ("schema_json", models.JSONField()),
                ("action", models.CharField(choices=[("generated", "Generated"), ("inline_edit", "Inline edit"), ("section_refine", "Section refinement"), ("imported", "Imported"), ("restored", "Restored")], max_length=24)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="website_revisions", to="auth.user")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="revisions", to="ai_builder.createdwebsite")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.RunPython(populate_website_persistence, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="websiterevision",
            constraint=models.UniqueConstraint(fields=("site", "revision_number"), name="unique_website_revision_number"),
        ),
        migrations.AlterField(
            model_name="createdwebsite",
            name="slug",
            field=models.SlugField(blank=True, max_length=160, unique=True),
        ),
    ]

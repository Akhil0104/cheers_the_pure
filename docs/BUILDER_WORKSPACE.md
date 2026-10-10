# SaaSsum AI Builder Workspace

## Run locally

1. Configure `GROQ_API_KEY` in the Django environment to enable generation and section
   refinement. Without it, the APIs return HTTP 503 with an actionable error; they do not
   fabricate generated content.
2. Apply the site-builder migration with `python manage.py migrate`.
3. Sign into the Django application and open `/builder/`.

The workspace uses the existing Django template and static-file stack. It does not add a second
frontend build system or use Tailwind CDN. Generated text is rendered with DOM APIs and
`textContent`; it is not inserted as trusted HTML.

## API routes

- `POST /api/site-builder/generate/` calls Groq, validates the complete `SiteSchema`, and saves
  the result to the authenticated user's account.
- `GET|POST /api/site-builder/sites/` lists owned sites or saves a validated site.
- `GET|PUT /api/site-builder/sites/<uuid>/` loads or updates an owned site.
- `POST /api/site-builder/refine/` calls Groq for one selected section, validates its schema,
  and persists only that section replacement.
- `POST /api/site-builder/sites/<uuid>/publish/` enables read-only access through a random
  share-token URL.
- Saved sites have a collision-safe slug and persisted schema version. Every successful
  generation, inline save, or section refinement creates an immutable `WebsiteRevision`
  snapshot with an action label and safe metadata.
- `POST /api/v1/inquiry/submit/` validates a B2B inquiry, then uses the shared quote workflow
   to create a pending `QuoteRequest`, email-verification token, and verification message. The
   browser displays confirmation only after persistence returns the real quote ID.

All API writes use Django session authentication and CSRF protection. Site reads and writes are
owner-scoped except for a published share URL. Share URLs expose only the public site schema,
never the original prompt or account information. Shared views are read-only, and quote-form
submission is disabled there; inquiries remain available from the signed-in builder preview.
The inquiry API additionally requires a B2B or staff account, an idempotency UUID, and is limited
to five submissions per user/IP per ten minutes. Configure a shared Django cache backend in
multi-worker production deployments; the local development default is process-local.

## Persistence migration

The builder persistence migration adds `CreatedWebsite.slug`, `CreatedWebsite.schema_version`,
and the `WebsiteRevision` table. It backfills existing sites with collision-safe migration
slugs and one `generated` snapshot of each current validated schema. It does not alter
products, inventory, quotes, orders, payments, or customer records.

Inspect and apply it safely from the repository root:

```powershell
python manage.py makemigrations ai_builder --check --dry-run
python manage.py migrate --plan
python manage.py migrate ai_builder
```

The first two commands are read-only. Before applying the final command in a shared or
production environment, take the normal database backup and schedule the schema change. Never
reset or recreate the database to apply this migration.

## Automated checks

Run the schema and endpoint tests with:

```powershell
python manage.py test ai_builder
```

The tests cover schema constraints, save/load and owner isolation, regeneration limited to one
section, publishing, quote persistence, and failure when the Groq service is unavailable.
Groq is mocked only in tests; production endpoints call the configured Groq client.

## Manual verification

1. Sign in, visit `/builder/`, and verify the empty-canvas state and disabled actions.
2. Enter a business prompt and generate. With a working Groq key, verify progress and the
   returned schema-driven page. With no key, verify a visible service error and no saved site.
3. Change the preview to Mobile and back; confirm the rendered content is unchanged.
4. Click editable text in the preview, change it, blur the field, and verify the unsaved state
   transitions to saved. Reload the saved website from the library and confirm the edit remains.
5. Select one section, submit an edit instruction, and confirm only that section changes.
6. Publish, open the copied share link in a signed-out window, and verify it is read-only.
7. Export HTML and open it offline. Text, layout, and bundled renderer styles should work;
   Google Fonts are network-loaded in the builder but are not required for layout.
8. Submit invalid and valid quote-form data. Invalid data must show a validation error; the
   confirmation must only appear after a successful backend response and persisted request.

## Export boundary

HTML export includes the current validated site schema and the trusted renderer/styles. It does
not include session cookies, private generation prompts, database records, or credentials.
Generation, account save/load, section regeneration, publish/share, and quote submission require
the live Django backend and will not work from the downloaded file. Remote images and Google
Fonts require network access. The browser's quote form validates for usability; the backend
validates every submitted field again.
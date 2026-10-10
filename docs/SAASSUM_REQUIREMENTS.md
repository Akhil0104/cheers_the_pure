# SaaSsum AI Challenge Requirements

**Assessment date:** 2026-10-10  
**Source of truth:** current repository source, tests, and builder documentation  
**Challenge premise:** A user describes the website they want, and the system generates a
complete website layout, content, and preview.

This document deliberately separates implementation evidence from assumptions. “Implemented”
means the capability is represented in source and covered by relevant automated tests where
applicable. It does not mean a live Groq/browser/staging demonstration has been independently
completed; the current baseline was executed without Groq or Hindsight credentials.

## Status summary

| Capability | Status | Evidence and limitation |
|---|---|---|
| Natural-language website creation | **Partially implemented** | [`workspace.html`](../ai_builder/templates/ai_builder/workspace.html) accepts a business brief and [`views.py`](../ai_builder/views.py) generates from it. This is a single prompt workflow, not a multi-turn chat conversation. |
| AI-generated layout and content | **Implemented** | Strict `SiteSchema`, Groq generation endpoint, schema validation, persistence, and tests exist in [`schemas.py`](../ai_builder/schemas.py), [`views.py`](../ai_builder/views.py), and [`tests.py`](../ai_builder/tests.py). Live Groq generation was not run. |
| Editable sections/content | **Implemented** | Browser inline editing and owned save/load APIs are present in [`app.js`](../ai_builder/static/ai_builder/app.js) and [`views.py`](../ai_builder/views.py). Browser acceptance was not independently run. |
| Section-level regeneration | **Implemented** | `refine_section` validates and persists only the selected section; automated test coverage verifies other sections remain unchanged. |
| Live responsive preview | **Partially implemented** | Desktop/mobile preview controls and renderer behavior exist. No browser smoke test was completed in this baseline, so visual responsiveness remains unverified. |
| Export or share link | **Implemented** | HTML export exists in the builder client; publishing creates a random-token, read-only share route. Tests cover publishing/share behavior. Export was not opened offline during this assessment. |
| Real CheersThePure catalog integration | **Partially implemented** | The schema has a trusted catalog-price boundary, but the canonical generated example uses sample products and no builder-side server enrichment from `Product`/`Inventory` was verified. |
| Real B2B inquiry workflow | **Implemented** | Builder inquiry API validates B2B/staff access, idempotency, rate limits, and persists the existing quote workflow; tests cover quote/token/dashboard records. |
| Visible truthful agent activity | **Partially implemented** | Generation progress/status messaging is visible, but no complete, user-facing trace of schema validation, persistence, or catalog/inquiry actions was verified. |
| Saved drafts | **Implemented** | `CreatedWebsite` ownership, list/load/save/update APIs, and a saved-sites library exist. |
| Revision recovery | **Not implemented** | Sites have timestamps but no revision model, revision API, undo/restore history, or version comparison was verified. |
| Website validation and safe rendering | **Implemented** | Strict Pydantic validation, allowlists, provenance checks, text rendering, owner isolation, CSRF/session checks, and security tests exist. |

## 1. User stories

### Primary creation journey

1. **As a business owner**, I want to describe my business and desired website in natural
   language so that I can start without knowing HTML or CSS.
2. **As a business owner**, I want the system to generate a complete page structure and usable
   copy so that I can evaluate a first draft quickly.
3. **As a business owner**, I want to see the generated site in a live canvas so that I can
   understand the result before sharing it.
4. **As a business owner**, I want desktop and mobile previews so that I can catch layout
   problems on both screen sizes.
5. **As a business owner**, I want to edit text in place so that I can make small corrections
   without regenerating the whole website.
6. **As a business owner**, I want to select one section and ask AI to change only that section
   so that approved content elsewhere is preserved.
7. **As a business owner**, I want to save and reload my draft so that I can continue later.
8. **As a business owner**, I want to export or publish a share link so that I can show the
   result to others.

### CheersThePure differentiators

9. **As a wholesale buyer**, I want generated product content to use verified CheersThePure
   catalog data so that prices and availability are not invented.
10. **As an eligible B2B user**, I want to submit an inquiry from the generated site so that it
    enters the existing quote workflow.
11. **As a user**, I want truthful progress and result messages so that I can tell whether AI
    generation, validation, saving, publishing, or inquiry submission actually succeeded.
12. **As a returning owner**, I want to recover an earlier saved version so that an experimental
    edit cannot destroy approved work.

## 2. Functional requirements

### Creation and generation

**FR-01 — Brief input (Partial).** The workspace MUST accept a bounded natural-language
business brief. The current UI provides a required textarea capped at 4,000 characters.
To satisfy the strict chat requirement, a future implementation SHOULD support conversational
follow-up turns or clearly scope the MVP as “single-turn prompt generation.”

**FR-02 — Generation request (Implemented).** An authenticated user MUST be able to submit a
brief to the generation endpoint. The service MUST call the configured Groq integration,
reject unavailable service responses as an explicit error, and never fabricate a successful
generated site.

**FR-03 — Complete schema output (Implemented).** Generated output MUST validate against
`SiteSchema`: supported section types, unique IDs, bounded collections/content, allowlisted
actions/icons/themes, and safe URLs. Invalid model output MUST not be persisted.

**FR-04 — Generated page preview (Implemented, browser verification pending).** A valid site
MUST render through the schema-driven renderer with hero, features, product grid, quote form,
footer, text, or testimonial sections as applicable.

### Editing and refinement

**FR-05 — Inline editing (Implemented, browser verification pending).** Editable text changes
MUST update the current schema, show an unsaved/saved state, and persist only after a valid
save request.

**FR-06 — Section refinement (Implemented).** A user MUST select one section and submit an
instruction. The response MUST replace only that section, preserve its ID/type constraints,
revalidate the complete site, and leave all other sections unchanged.

**FR-07 — Draft library (Implemented).** Authenticated users MUST list, load, create, and
update only their own saved sites. The library MUST not expose another user’s prompt or schema.

**FR-08 — Revision recovery (Not implemented).** The product SHOULD retain immutable revisions
and provide restore/compare controls. The current `CreatedWebsite` model stores only the latest
schema and timestamps, so this requirement is not satisfied yet.

### Preview, publish, and export

**FR-09 — Responsive modes (Partial).** The UI MUST offer desktop and mobile preview modes and
preserve content while changing presentation. Existing controls and state exist; browser
verification remains required.

**FR-10 — Share link (Implemented).** Publishing MUST create or reuse a random share token and
expose a read-only public route containing only public schema data. The shared view MUST not
permit editing or inquiry submission.

**FR-11 — HTML export (Implemented, manual verification pending).** The user MUST be able to
download the current validated schema as standalone renderer HTML. The export MUST not include
session cookies, credentials, private prompts, or database records. Remote assets may require
network access as documented.

### CheersThePure integration

**FR-12 — Trusted catalog enrichment (Partial).** Live product data MUST come from server-side
`Product`/`Inventory` records. An LLM or browser MUST NOT be allowed to assert that sample data
is database data or set an arbitrary price. Current schema safeguards cover the trust boundary,
but builder generation/enrichment from the live catalog was not verified.

**FR-13 — B2B inquiry (Implemented).** A valid generated quote form MUST submit through the
trusted inquiry endpoint, require an authenticated B2B/staff account, validate fields, require
an idempotency UUID, apply rate limiting, and persist the existing pending `QuoteRequest`,
verification token, and notification workflow.

### Activity and truthfulness

**FR-14 — User-visible status (Partial).** The UI MUST show truthful states for generating,
validation failure, service unavailable, saving, publishing, exporting, and inquiry submission.
The current UI has progress and feedback messages, but a complete action trace has not been
verified.

**FR-15 — No false success (Implemented).** Backend and client behavior MUST display success only
after the corresponding validated/persisted response. Existing tests cover unavailable
generation, inquiry persistence errors, and generic safe error responses.

## 3. Security requirements

**SEC-01 — Authentication.** Workspace generation, save/load/update, refinement, publishing,
and inquiry submission MUST require the appropriate authenticated session. Public access is
limited to explicitly published share links.

**SEC-02 — Authorization and tenant isolation.** A user MUST access only their own
`CreatedWebsite` records. Non-staff users MUST NOT override B2B buyer identity or access other
users’ DispatchAI/memory data.

**SEC-03 — CSRF and request boundaries.** Browser write endpoints MUST retain Django session and
CSRF protection. JSON endpoints MUST validate method, content type, body size, and required
fields.

**SEC-04 — Schema allowlisting.** Reject unknown fields, unsupported section types, unsafe
markup-like content, event-handler-like strings, unsafe URLs, duplicate IDs, invalid image
URLs, and untrusted catalog claims.

**SEC-05 — Safe rendering.** Render generated text as text/contextually escaped content; never
execute generated HTML, JavaScript, CSS, iframe markup, server-side code, or arbitrary action
URLs.

**SEC-06 — Provenance.** Sample products MUST NOT carry prices. Live catalog prices MUST be
independently looked up and represented with integer minor units and provenance metadata.
Unverified testimonials, certifications, laboratory results, and purification claims MUST not
be presented as verified facts.

**SEC-07 — Secret and private-data protection.** Responses, exports, share pages, logs, and
activity displays MUST not contain API keys, session cookies, private prompts, account details,
raw database IDs, or unrelated customer data.

**SEC-08 — Abuse controls.** Inquiry and generation surfaces SHOULD retain bounded input sizes,
rate limits, idempotency for inquiry submission, and explicit service failure handling. Shared
cache configuration MUST be used for multi-worker production deployments.

## 4. Acceptance criteria

### End-to-end MVP journey

The MVP is accepted only when all of the following pass in a configured staging environment:

1. Sign in as an eligible user and open `/builder/`.
2. Enter a business brief and submit it.
3. Observe a truthful progress state; receive either a valid generated site or an explicit
   service error. No fake successful site may be saved when Groq is unavailable.
4. Confirm the generated site contains a valid, rendered multi-section layout and content.
5. Switch Desktop → Mobile → Desktop; content remains unchanged and the layout remains usable.
6. Edit a text field, observe an unsaved state, save, reload the site, and confirm the edit
   persists.
7. Select one section, refine it, and confirm only that section changes.
8. Reload the site from the saved-sites library and confirm owner-scoped persistence.
9. Publish and open the share URL signed out; confirm the page is read-only and contains no
   private prompt/account data.
10. Export HTML, open it locally, and confirm the current text/layout renders without session
    cookies or credentials. Document any expected remote-asset limitations.
11. Submit invalid inquiry data and confirm a validation error with no quote created.
12. Submit valid inquiry data as an eligible B2B user and confirm the real pending quote,
    verification token, and dashboard record are created exactly once for an idempotent retry.

### Safety and regression acceptance

- `python manage.py check` passes with no unresolved blocking issues.
- `python manage.py migrate --plan` reports no unexpected operations.
- The existing full suite remains green at the current baseline of 113 tests.
- Schema security tests continue to reject markup, event handlers, unsafe URLs, unknown fields,
  duplicate IDs, untrusted prices, and false testimonial provenance.
- An anonymous or B2C user cannot submit the B2B inquiry endpoint.
- A user cannot load, update, publish, or refine another user’s site.
- Groq/Hindsight/Stripe outages produce explicit safe failure behavior and do not create
  success-shaped records.

## 5. Out of scope for the MVP

Unless the challenge rubric explicitly adds them, the following are out of scope:

- Full multi-turn conversational memory or a general-purpose autonomous website agent
- Arbitrary custom HTML/CSS/JavaScript injection
- Custom domains, DNS automation, SSL provisioning, and hosting/CDN deployment
- SaaS subscriptions, metering, billing, team seats, and organization administration
- Drag-and-drop freeform design tooling
- Pixel-perfect Figma/Canva parity
- Production analytics, SEO dashboards, A/B testing, or conversion attribution
- Real-time multi-user collaboration and conflict resolution
- Automatic image generation, asset licensing, or local asset mirroring
- Live payment collection from generated websites
- Migration from or import of third-party websites
- Full revision history, diffing, branching, or undo/redo beyond the current draft
- Hindsight memory for ordinary SaaSsum website drafts unless explicitly required by the rubric

## 6. Demonstration checklist

### Before the demo

- [ ] Use a supported Python environment and verify `python manage.py check`.
- [ ] Verify `python manage.py migrate --plan` is clean.
- [ ] Run `python manage.py test --verbosity 1`; record the result.
- [ ] Configure Groq only in a secret-safe staging environment; do not display the key.
- [ ] Prepare a test B2B account and a separate B2C/anonymous account.
- [ ] Ensure test catalog records and inquiry email behavior are non-production.
- [ ] Confirm browser console/network views will not expose credentials or private data.

### Primary demo

- [ ] Sign in and show the empty builder state with disabled actions.
- [ ] Submit a brief such as: “Create a clean wholesale water supplier website for
  CheersThePure with product sizes, a business inquiry form, and a trustworthy professional
  tone.”
- [ ] Show generation progress and the resulting hero, features, product grid, inquiry form,
  and footer.
- [ ] Toggle desktop/mobile preview and point out that the content is unchanged.
- [ ] Edit one headline inline, save, reload, and show persistence.
- [ ] Select one section and regenerate it; show that unrelated sections remain unchanged.
- [ ] Open the saved-sites library and reload the draft.
- [ ] Publish, copy the share link, open it signed out, and demonstrate read-only behavior.
- [ ] Export HTML and open it locally; explain that backend actions still require the live
  application.

### Differentiator demo

- [ ] Show that generated sample products do not claim live prices by default.
- [ ] If trusted catalog enrichment is available in the configured build, show the server-side
  product source and verified price; otherwise state clearly that this differentiator is
  partial and do not present sample values as live catalog data.
- [ ] Submit invalid inquiry data and show the validation error.
- [ ] Submit valid inquiry data as the B2B test account.
- [ ] Show the resulting pending quote in the existing dashboard, not merely a browser toast.
- [ ] Retry with the same idempotency key and show that no duplicate quote is created.
- [ ] Show truthful status messages for success and a simulated unavailable-AI failure path.

### Closeout

- [ ] Confirm no API keys, session cookies, private prompts, or other user data appeared in
  the UI, exported file, share page, logs, or screen recording.
- [ ] Report honestly which items were live-verified, test-verified, or not demonstrated.
- [ ] If revision recovery is requested by judges, explicitly identify it as not implemented
  rather than implying that saved drafts provide historical recovery.

## Priority order

1. Complete and browser-verify the single end-to-end journey: prompt → valid generated site →
   edit → section refine → save → share/export.
2. Preserve schema validation, safe rendering, ownership, and truthful failure behavior.
3. Verify the real B2B inquiry connection and idempotency in staging.
4. Add server-side CheersThePure catalog enrichment only with explicit provenance.
5. Add a conversational chat experience, richer activity trace, and revision recovery only
   after the core journey is reliable.

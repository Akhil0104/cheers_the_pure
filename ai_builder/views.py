import json
import logging
import uuid
from hashlib import sha256

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from pydantic import ValidationError

from app.account_utils import detect_account_type
from app.quote_services import IdempotencyConflict, create_quote_request_workflow
from dispatch import groq_client

from .builder_prompts import GENERATION_SYSTEM_PROMPT, build_section_refine_system_prompt
from .models import CreatedWebsite, WebsiteRevision
from .provider import WebsiteAIProvider, WebsiteProviderError
from .schemas import InquirySubmission, SECTION_MODELS, SiteSchema

logger = logging.getLogger(__name__)


def _json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message}, status=status)


def _provider_error(error: WebsiteProviderError) -> JsonResponse:
    status = 429 if error.code == "rate_limited" else 503 if error.code == "provider_unavailable" else 502
    return _json_error(str(error), status)


def _request_json(request) -> dict:
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as error:
        raise ValueError("Request body must be valid JSON.") from error
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


def _owned_site(request, site_id):
    return get_object_or_404(CreatedWebsite, site_id=site_id, owner=request.user)


def _serialize_site(site: CreatedWebsite) -> dict:
    return {
        "site_id": str(site.site_id),
        "slug": site.slug,
        "site": site.schema_json,
        "schema_version": site.schema_version,
        "prompt": site.prompt,
        "is_published": site.is_published,
        "share_url": f"/builder/share/{site.share_token}/" if site.is_published else None,
        "created_at": site.created_at.isoformat(),
        "updated_at": site.updated_at.isoformat(),
    }


def _save_site_with_revision(
    site: CreatedWebsite,
    validated_site: SiteSchema,
    action: str,
    metadata: dict | None = None,
) -> WebsiteRevision:
    site.site_name = validated_site.site_name
    site.brand_name = validated_site.brand.name
    site.theme = validated_site.theme.color
    site.schema_version = validated_site.schema_version
    site.schema_json = validated_site.model_dump(mode="json")
    with transaction.atomic():
        site.save()
        previous = (
            WebsiteRevision.objects.select_for_update()
            .filter(site=site)
            .order_by("-revision_number")
            .first()
        )
        revision = WebsiteRevision.objects.create(
            site=site,
            revision_number=(previous.revision_number + 1) if previous else 1,
            schema_version=site.schema_version,
            schema_json=site.schema_json,
            action=action,
            metadata=metadata or {},
            created_by=site.owner,
        )
    return revision


def _validated_json_object(text: str) -> dict:
    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"The AI response contains a duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        result = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("The AI response was not valid JSON. Please try again.") from error
    if not isinstance(result, dict):
        raise ValueError("The AI response must be one JSON object.")
    return result


def _has_untrusted_site_data(site: SiteSchema, trusted_site_data: dict | None = None) -> bool:
    trusted_products = set()
    trusted_testimonials = set()
    if trusted_site_data:
        for section in trusted_site_data.get("sections", []):
            if section.get("type") == "product_grid":
                trusted_products.update(
                    json.dumps(product, sort_keys=True)
                    for product in section.get("items", [])
                    if product.get("data_source") == "cheersthepure_database"
                )
            elif section.get("type") == "testimonials":
                trusted_testimonials.update(
                    json.dumps(item, sort_keys=True)
                    for item in section.get("items", [])
                    if item.get("content_status") == "verified"
                )

    for section in site.sections:
        if section.type == "product_grid":
            for product in section.items:
                if product.data_source == "cheersthepure_database":
                    if json.dumps(product.model_dump(mode="json"), sort_keys=True) not in trusted_products:
                        return True
        elif section.type == "testimonials":
            for item in section.items:
                if item.content_status == "verified":
                    if json.dumps(item.model_dump(mode="json"), sort_keys=True) not in trusted_testimonials:
                        return True
    return False


@login_required
@require_GET
def workspace(request):
    inquiry_url = settings.SAASSUM_INQUIRY_API_URL
    if not inquiry_url.startswith("/") or inquiry_url.startswith("//"):
        inquiry_url = "/api/v1/inquiry/submit/"
    return render(request, "ai_builder/workspace.html", {"inquiry_api_url": inquiry_url})


@require_GET
def shared_site(request, share_token):
    site = get_object_or_404(
        CreatedWebsite,
        share_token=share_token,
        is_published=True,
    )
    return render(request, "ai_builder/shared_site.html", {"site_data": site.schema_json})


@login_required
@require_http_methods(["GET", "POST"])
def site_collection(request):
    if request.method == "GET":
        sites = CreatedWebsite.objects.filter(owner=request.user).order_by("-updated_at")[:50]
        return JsonResponse({"ok": True, "sites": [_serialize_site(site) for site in sites]})

    try:
        data = _request_json(request)
        site_data = data.get("site")
        validated_site = SiteSchema.model_validate(site_data)
    except (ValueError, ValidationError) as error:
        message = error.errors(include_context=False) if isinstance(error, ValidationError) else str(error)
        return JsonResponse({"ok": False, "error": message}, status=400)

    site_id = validated_site.site_id
    site = CreatedWebsite.objects.filter(site_id=site_id, owner=request.user).first()
    if site is None and CreatedWebsite.objects.filter(site_id=site_id).exists():
        return _json_error("That site ID is already in use.", 409)
    if _has_untrusted_site_data(validated_site, site.schema_json if site else None):
        return _json_error("Live product and verified testimonial data must come from trusted backend records.", 400)

    is_new_site = site is None
    if is_new_site:
        site = CreatedWebsite(site_id=site_id, owner=request.user)
    site.prompt = str(data.get("prompt", site.prompt if site.pk else ""))[:10000]
    _save_site_with_revision(
        site,
        validated_site,
        WebsiteRevision.Action.GENERATED if is_new_site else WebsiteRevision.Action.INLINE_EDIT,
        {"source": "site_collection"},
    )
    return JsonResponse({"ok": True, "saved_site": _serialize_site(site)})


@login_required
@require_http_methods(["GET", "PUT"])
def site_detail(request, site_id):
    site = _owned_site(request, site_id)
    if request.method == "GET":
        return JsonResponse({"ok": True, "saved_site": _serialize_site(site)})

    try:
        data = _request_json(request)
        validated_site = SiteSchema.model_validate(data.get("site"))
    except (ValueError, ValidationError) as error:
        message = error.errors(include_context=False) if isinstance(error, ValidationError) else str(error)
        return JsonResponse({"ok": False, "error": message}, status=400)
    if validated_site.site_id != site.site_id:
        return _json_error("The site ID cannot be changed.", 400)
    if _has_untrusted_site_data(validated_site, site.schema_json):
        return _json_error("Live product and verified testimonial data must come from trusted backend records.", 400)

    _save_site_with_revision(
        site,
        validated_site,
        WebsiteRevision.Action.INLINE_EDIT,
        {"source": "site_detail"},
    )
    return JsonResponse({"ok": True, "saved_site": _serialize_site(site)})


@login_required
@require_POST
def generate_site(request):
    try:
        data = _request_json(request)
        prompt = data.get("prompt", "")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
            return _json_error("Describe the site in 1-4000 characters.")
        site_id = str(uuid.uuid4())
        user_message = json.dumps(
            {"site_id": site_id, "request": prompt.strip()},
            ensure_ascii=False,
        )
        completion = WebsiteAIProvider().generate_json(
            messages=[
                {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            actor_key=f"user:{request.user.pk}",
            max_tokens=5000,
        )
        site_data = _validated_json_object(completion.get("content", ""))
        validated_site = SiteSchema.model_validate(site_data)
        if str(validated_site.site_id) != site_id:
            return _json_error("The generated site failed its identity check. Please retry.", 502)
        if _has_untrusted_site_data(validated_site):
            return _json_error("AI output cannot supply live products, prices, or verified testimonials.", 502)
    except (ValueError, ValidationError) as error:
        message = error.errors(include_context=False) if isinstance(error, ValidationError) else str(error)
        return JsonResponse({"ok": False, "error": message}, status=502)
    except WebsiteProviderError as error:
        logger.warning("Website generation provider failure: %s", error.code)
        return _provider_error(error)
    except RuntimeError as error:
        logger.warning("Website generation unavailable: %s", error)
        return _json_error("Website generation is unavailable. Check the Groq configuration and try again.", 503)
    except Exception:
        logger.exception("Website generation failed")
        return _json_error("Website generation failed. Please try again.", 502)

    site = CreatedWebsite(
        site_id=validated_site.site_id,
        owner=request.user,
        prompt=prompt.strip(),
    )
    _save_site_with_revision(site, validated_site, WebsiteRevision.Action.GENERATED, {"source": "generate"})
    return JsonResponse({"ok": True, "saved_site": _serialize_site(site)})


@login_required
@require_POST
def refine_section(request):
    try:
        data = _request_json(request)
        site = _owned_site(request, uuid.UUID(str(data.get("site_id"))))
        section_id = data.get("section_id")
        instruction = data.get("instruction", "")
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 2000:
            return _json_error("Enter a section instruction of 1-2000 characters.")
        section_index = next(
            (index for index, section in enumerate(site.schema_json["sections"]) if section["id"] == section_id),
            None,
        )
        if section_index is None:
            return _json_error("Section not found.", 404)
        current_section = site.schema_json["sections"][section_index]
        completion = WebsiteAIProvider().generate_json(
            messages=[
                {"role": "system", "content": build_section_refine_system_prompt(current_section["type"])},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"current_section": current_section, "instruction": instruction.strip()},
                        ensure_ascii=False,
                    ),
                },
            ],
            actor_key=f"user:{request.user.pk}",
            max_tokens=2000,
        )
        replacement = _validated_json_object(completion.get("content", ""))
        if replacement.get("id") != section_id or replacement.get("type") != current_section["type"]:
            return _json_error("The generated edit changed the section identity or type.", 502)
        section_model = SECTION_MODELS[current_section["type"]]
        validated_section = section_model.model_validate(replacement)
        updated_data = json.loads(json.dumps(site.schema_json))
        updated_data["sections"][section_index] = validated_section.model_dump(mode="json")
        validated_site = SiteSchema.model_validate(updated_data)
        if _has_untrusted_site_data(validated_site, site.schema_json):
            return _json_error("Section refinement cannot create or alter trusted business records.", 502)
    except Http404:
        return _json_error("Site not found.", 404)
    except (ValueError, ValidationError) as error:
        message = error.errors(include_context=False) if isinstance(error, ValidationError) else str(error)
        return JsonResponse({"ok": False, "error": message}, status=502)
    except CreatedWebsite.DoesNotExist:
        return _json_error("Site not found.", 404)
    except WebsiteProviderError as error:
        logger.warning("Section refinement provider failure: %s", error.code)
        return _provider_error(error)
    except RuntimeError as error:
        logger.warning("Section refinement unavailable: %s", error)
        return _json_error("Section refinement is unavailable. Check the Groq configuration and try again.", 503)
    except Exception:
        logger.exception("Section refinement failed")
        return _json_error("Section update failed. Please try again.", 502)

    _save_site_with_revision(
        site,
        validated_site,
        WebsiteRevision.Action.SECTION_REFINE,
        {"source": "refine_section", "section_id": section_id},
    )
    return JsonResponse({"ok": True, "section": site.schema_json["sections"][section_index]})


@login_required
@require_POST
def publish_site(request, site_id):
    site = _owned_site(request, site_id)
    if site.share_token is None:
        site.share_token = uuid.uuid4()
    site.is_published = True
    site.save(update_fields=["share_token", "is_published", "updated_at"])
    return JsonResponse({"ok": True, "saved_site": _serialize_site(site)})


def submit_inquiry(request):
    if request.method != "POST":
        response = _json_error("Use POST to submit an inquiry.", 405)
        response["Allow"] = "POST"
        return response
    if not request.user.is_authenticated:
        return _json_error("Authentication required.", 403)
    profile = getattr(request.user, "profile", None)
    account_type = profile.account_type if profile else detect_account_type(request.user.email)
    if not request.user.is_staff and account_type != "b2b":
        return _json_error("A B2B account is required to submit a wholesale inquiry.", 403)
    if request.content_type != "application/json":
        return _json_error("Content-Type must be application/json.")
    if len(request.body) > 16_384:
        return _json_error("Inquiry request body is too large.")

    remote_addr = request.META.get("REMOTE_ADDR", "unknown")
    rate_key = sha256(f"{request.user.pk}:{remote_addr}".encode("utf-8")).hexdigest()
    cache_key = f"saassum_inquiry_rate:{rate_key}"
    try:
        if not cache.add(cache_key, 1, timeout=600):
            try:
                count = cache.incr(cache_key)
            except ValueError:
                if cache.add(cache_key, 1, timeout=600):
                    count = 1
                else:
                    count = cache.incr(cache_key)
            if count > 5:
                response = _json_error("Too many inquiries. Please wait before trying again.", 429)
                response["Retry-After"] = "600"
                return response
    except Exception:
        logger.warning("Inquiry rate limiter unavailable; rejecting request.")
        return _json_error("Inquiry service is temporarily unavailable.", 503)

    try:
        data = _request_json(request)
    except ValueError as error:
        return _json_error(str(error))
    try:
        inquiry = InquirySubmission.model_validate(data)
    except ValidationError:
        return _json_error("Check the inquiry fields and try again.")

    try:
        idempotency_key = str(uuid.UUID(request.headers.get("Idempotency-Key", "")))
    except (ValueError, TypeError, AttributeError):
        return _json_error("A valid UUID Idempotency-Key header is required.")

    try:
        quote, created = create_quote_request_workflow(
            request=request,
            user=request.user,
            name=inquiry.name,
            email=str(inquiry.email).casefold(),
            company=inquiry.company,
            size=inquiry.normalized_size,
            quantity=inquiry.quantity,
            details=inquiry.details,
            idempotency_key=idempotency_key,
        )
    except IdempotencyConflict:
        return _json_error("That inquiry key was already used for different form data.", 409)
    except Exception:
        logger.error("B2B inquiry could not be persisted.")
        return _json_error("The inquiry could not be saved. Please try again.", 500)

    return JsonResponse(
        {
            "success": True,
            "quote_id": quote.pk,
            "message": "Quote request received",
            "status": quote.status,
        },
        status=201 if created else 200,
    )
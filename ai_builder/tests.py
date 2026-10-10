import unittest
from copy import deepcopy
import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.core import mail
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse
from pydantic import ValidationError

from app.models import EmailVerificationToken, QuoteRequest, UserProfile
from dispatch.models import ConversationSession

from .schema_examples import CHEERSTHEPURE_EXAMPLE
from .models import CreatedWebsite, WebsiteRevision
from .provider import (
    MockWebsiteAIProvider,
    WebsiteAIProvider,
    WebsiteProviderError,
    WebsiteProviderMalformedResponse,
    WebsiteProviderRateLimited,
    WebsiteProviderUnavailable,
    WebsiteProviderSettings,
)
from .generation import generate_validated_site, normalize_generation_brief
from .quality import review_site
from .orchestrator import ActivityTrace, orchestrate_generation, plan_website
from .schemas import SiteSchema
from .views import _validated_json_object


class SiteSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = deepcopy(CHEERSTHEPURE_EXAMPLE)

    def test_valid_cheersthepure_sample(self) -> None:
        site = SiteSchema.model_validate(self.payload)
        self.assertEqual(site.schema_version, "1.0")
        self.assertEqual(len(site.sections), 5)
        products = site.sections[2]
        self.assertEqual([product.capacity for product in products.items], ["250 ml", "500 ml", "1 L", "2 L"])
        self.assertTrue(all(product.data_source == "sample" and product.price is None for product in products.items))

    def test_missing_required_field_is_rejected(self) -> None:
        del self.payload["brand"]
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_unknown_top_level_field_is_rejected(self) -> None:
        self.payload["unexpected"] = "not allowed"
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_unknown_theme_color_is_rejected(self) -> None:
        self.payload["theme"]["color"] = "orange"
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_duplicate_section_ids_are_rejected(self) -> None:
        self.payload["sections"][1]["id"] = self.payload["sections"][0]["id"]
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_excessive_section_count_is_rejected(self) -> None:
        self.payload["sections"] = self.payload["sections"] * 3
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_excessive_text_length_is_rejected(self) -> None:
        self.payload["site_name"] = "x" * 121
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_excessive_document_size_is_rejected(self) -> None:
        self.payload["sections"][0]["subheadline"] = "x" * 100_001
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_unknown_section_type_is_rejected(self) -> None:
        self.payload["sections"][0]["type"] = "custom_html"
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_invalid_image_url_is_rejected(self) -> None:
        self.payload["sections"][0]["image_url"] = "javascript:alert(1)"
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_invalid_footer_url_is_rejected(self) -> None:
        self.payload["sections"][4]["links"][0]["url"] = "//evil.example/path"
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_valid_external_footer_url_is_accepted(self) -> None:
        self.payload["sections"][4]["links"][0]["url"] = "https://example.com/products"
        site = SiteSchema.model_validate(self.payload)
        self.assertEqual(site.sections[4].links[0].url, "https://example.com/products")

    def test_markup_like_content_is_rejected(self) -> None:
        self.payload["sections"][0]["headline"] = "<script>alert(1)</script>"
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_event_handler_like_content_is_rejected(self) -> None:
        self.payload["sections"][0]["headline"] = "onclick=alert(1)"
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_image_url_with_embedded_credentials_is_rejected(self) -> None:
        self.payload["sections"][0]["image_url"] = "https://user:pass@example.com/image.jpg"
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_arbitrary_quote_endpoint_is_not_a_schema_field(self) -> None:
        self.payload["sections"][3]["api_url"] = "https://attacker.example/collect"
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_sample_product_cannot_claim_a_price(self) -> None:
        self.payload["sections"][2]["items"][0]["price"] = {
            "amount": "10.00",
            "currency": "INR",
            "source": "cheersthepure_database",
        }
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_trusted_database_price_uses_integer_minor_units(self) -> None:
        product = self.payload["sections"][2]["items"][0]
        product["data_source"] = "cheersthepure_database"
        product["price"] = {
            "amount_minor": 1025,
            "currency": "INR",
            "source": "cheersthepure_database",
        }
        site = SiteSchema.model_validate(self.payload)
        self.assertEqual(site.sections[2].items[0].price.amount_minor, 1025)

    def test_valid_catalog_binding_is_strictly_typed(self) -> None:
        product = self.payload["sections"][2]["items"][0]
        product["data_binding"] = {
            "source": "cheersthepure_catalog",
            "entity": "product",
            "key": "capacity",
            "value": "500 ml",
        }
        site = SiteSchema.model_validate(self.payload)
        self.assertEqual(site.sections[2].items[0].data_binding.key, "capacity")

    def test_unsafe_catalog_binding_is_rejected(self) -> None:
        product = self.payload["sections"][2]["items"][0]
        product["data_binding"] = {
            "source": "https://attacker.example/catalog",
            "entity": "product",
            "key": "capacity",
            "value": "500 ml",
        }
        with self.assertRaises(ValidationError):
            SiteSchema.model_validate(self.payload)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _validated_json_object('{"site_name":"first","site_name":"second"}')


class WebsiteProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.config = WebsiteProviderSettings(
            timeout_seconds=2,
            max_output_chars=100,
            rate_limit=2,
            rate_window_seconds=60,
        )

    @patch("ai_builder.provider.is_groq_configured", return_value=True)
    def test_successful_output_is_bounded(self, configured) -> None:
        provider = WebsiteAIProvider(
            chat=lambda **kwargs: {"content": '{"sections":[]}', "model": "test"},
            config=self.config,
        )
        response = provider.generate_json(messages=[], actor_key="test-user", max_tokens=20)
        self.assertEqual(response["content"], '{"sections":[]}')

    @patch("ai_builder.provider.is_groq_configured", return_value=True)
    def test_timeout_is_recoverable(self, configured) -> None:
        provider = WebsiteAIProvider(chat=lambda **kwargs: (_ for _ in ()).throw(TimeoutError()), config=self.config)
        with self.assertRaises(WebsiteProviderError) as raised:
            provider.generate_json(messages=[], actor_key="timeout-user", max_tokens=20)
        self.assertEqual(raised.exception.code, "timeout")

    @patch("ai_builder.provider.is_groq_configured", return_value=True)
    def test_provider_failure_is_recoverable(self, configured) -> None:
        provider = WebsiteAIProvider(
            chat=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("upstream failed")),
            config=self.config,
        )
        with self.assertRaises(WebsiteProviderError) as raised:
            provider.generate_json(messages=[], actor_key="failure-user", max_tokens=20)
        self.assertEqual(raised.exception.code, "provider_error")

    @patch("ai_builder.provider.is_groq_configured", return_value=True)
    def test_malformed_output_is_rejected(self, configured) -> None:
        provider = WebsiteAIProvider(chat=lambda **kwargs: {"content": ""}, config=self.config)
        with self.assertRaises(WebsiteProviderMalformedResponse):
            provider.generate_json(messages=[], actor_key="malformed-user", max_tokens=20)

    @patch("ai_builder.provider.is_groq_configured", return_value=False)
    def test_missing_configuration_is_recoverable(self, configured) -> None:
        provider = WebsiteAIProvider(config=self.config)
        with self.assertRaises(WebsiteProviderUnavailable):
            provider.generate_json(messages=[], actor_key="missing-user", max_tokens=20)

    @patch("ai_builder.provider.is_groq_configured", return_value=True)
    def test_rate_limit_is_enforced(self, configured) -> None:
        provider = WebsiteAIProvider(
            chat=lambda **kwargs: {"content": "{}", "model": "test"},
            config=self.config,
        )
        provider.generate_json(messages=[], actor_key="limited-user", max_tokens=20)
        provider.generate_json(messages=[], actor_key="limited-user", max_tokens=20)
        with self.assertRaises(WebsiteProviderRateLimited):
            provider.generate_json(messages=[], actor_key="limited-user", max_tokens=20)

    def test_mock_provider_never_requires_configuration(self) -> None:
        provider = MockWebsiteAIProvider({"content": "{}", "model": "mock"})
        self.assertEqual(
            provider.generate_json(messages=[], actor_key="mock-user", max_tokens=20)["model"],
            "mock",
        )


class WebsiteGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = deepcopy(CHEERSTHEPURE_EXAMPLE)
        self.site_id = str(self.payload["site_id"])
        self.brief = {
            "business_description": "A bottled water supplier",
            "audience": "Hotels and restaurants",
            "goal": "Collect wholesale inquiries",
            "visual_direction": "Clean and calm",
            "requested_sections": ["hero", "product_grid", "quote_form"],
        }

    def test_valid_generation_returns_validated_schema(self) -> None:
        provider = MockWebsiteAIProvider({"content": json.dumps(self.payload)})
        site = generate_validated_site(
            provider=provider,
            site_id=self.site_id,
            brief=self.brief,
            actor_key="generation-valid",
        )
        self.assertEqual(site.site_id, uuid.UUID(self.site_id))

    def test_invalid_json_is_repaired(self) -> None:
        payload = self.payload

        class RepairProvider:
            def __init__(self):
                self.calls = 0

            def generate_json(self, **kwargs):
                self.calls += 1
                content = "not json" if self.calls == 1 else json.dumps(payload)
                return {"content": content}

        provider = RepairProvider()
        site = generate_validated_site(
            provider=provider,
            site_id=self.site_id,
            brief=self.brief,
            actor_key="generation-repair",
        )
        self.assertEqual(provider.calls, 2)
        self.assertEqual(site.site_id, uuid.UUID(self.site_id))

    def test_unsupported_requested_section_is_rejected_before_provider(self) -> None:
        with self.assertRaises(ValueError):
            normalize_generation_brief({**self.brief, "requested_sections": ["custom_html"]})

    def test_unsafe_link_is_rejected(self) -> None:
        unsafe = deepcopy(self.payload)
        unsafe["sections"][4]["links"][0]["url"] = "javascript:alert(1)"
        provider = MockWebsiteAIProvider({"content": json.dumps(unsafe)})
        with self.assertRaises(ValidationError):
            generate_validated_site(
                provider=provider,
                site_id=self.site_id,
                brief=self.brief,
                actor_key="generation-unsafe",
                max_repair_attempts=0,
            )

    def test_missing_field_is_rejected_after_repair_limit(self) -> None:
        missing = deepcopy(self.payload)
        del missing["brand"]
        provider = MockWebsiteAIProvider({"content": json.dumps(missing)})
        with self.assertRaises(ValidationError):
            generate_validated_site(
                provider=provider,
                site_id=self.site_id,
                brief=self.brief,
                actor_key="generation-missing",
            )

    def test_too_many_sections_is_rejected(self) -> None:
        oversized = deepcopy(self.payload)
        oversized["sections"] = oversized["sections"] * 3
        provider = MockWebsiteAIProvider({"content": json.dumps(oversized)})
        with self.assertRaises(ValidationError):
            generate_validated_site(
                provider=provider,
                site_id=self.site_id,
                brief=self.brief,
                actor_key="generation-sections",
                max_repair_attempts=0,
            )

    def test_provider_timeout_is_not_repaired(self) -> None:
        provider = WebsiteAIProvider(
            chat=lambda **kwargs: (_ for _ in ()).throw(TimeoutError()),
            config=WebsiteProviderSettings(rate_limit=10),
        )
        with self.assertRaises(WebsiteProviderError) as error:
            generate_validated_site(
                provider=provider,
                site_id=self.site_id,
                brief=self.brief,
                actor_key="generation-timeout",
            )
        self.assertEqual(error.exception.code, "timeout")


class WebsiteQualityReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = deepcopy(CHEERSTHEPURE_EXAMPLE)

    def test_valid_site_has_passing_review(self) -> None:
        site, review = review_site(self.payload)
        self.assertIsNotNone(site)
        self.assertTrue(review["ok"])
        self.assertEqual({check["status"] for check in review["checks"] if check["key"] == "schema"}, {"pass"})

    def test_quality_warnings_are_distinct_from_blocking_failures(self) -> None:
        self.payload["sections"][0]["headline"] = "The fastest guaranteed hydration"
        _, review = review_site(self.payload)
        statuses = {check["key"]: check["status"] for check in review["checks"]}
        self.assertEqual(statuses["factual_claims"], "warning")
        self.assertEqual(statuses["section_completeness"], "pass")
        self.assertTrue(review["ok"])

    def test_invalid_schema_is_blocking(self) -> None:
        self.payload["sections"][0]["type"] = "custom_html"
        site, review = review_site(self.payload)
        self.assertIsNone(site)
        self.assertFalse(review["ok"])
        self.assertIn("blocking", {check["status"] for check in review["checks"]})

    def test_untrusted_business_binding_is_blocking(self) -> None:
        product = self.payload["sections"][2]["items"][0]
        product["data_source"] = "cheersthepure_database"
        product["price"] = {
            "amount_minor": 100,
            "currency": "INR",
            "source": "cheersthepure_database",
        }
        _, review = review_site(self.payload)
        self.assertFalse(review["ok"])
        self.assertEqual(
            next(check["status"] for check in review["checks"] if check["key"] == "business_data_bindings"),
            "blocking",
        )


class WebsiteOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = deepcopy(CHEERSTHEPURE_EXAMPLE)
        self.brief = {
            "business_description": "A bottled water supplier",
            "audience": "Hotels",
            "goal": "Collect inquiries",
            "visual_direction": "Clean",
            "requested_sections": ["hero", "footer"],
        }

    def test_planner_handoff_and_activity_trace(self) -> None:
        plan = plan_website(self.brief)
        self.assertEqual(plan.section_types[:2], ("hero", "footer"))
        result = orchestrate_generation(
            provider=MockWebsiteAIProvider({"content": json.dumps(self.payload)}),
            site_id=str(self.payload["site_id"]),
            brief=self.brief,
            actor_key="orchestration-success",
        )
        stages = [event["stage"] for event in result.activity]
        self.assertEqual(stages, ["planning", "catalog", "generation", "validation", "preview"])
        self.assertTrue(all(event["summary"] for event in result.activity))

    def test_invalid_output_records_repair_and_failure(self) -> None:
        provider = MockWebsiteAIProvider({"content": '{"unsupported": true}'})
        with self.assertRaises(ValidationError):
            orchestrate_generation(
                provider=provider,
                site_id=str(self.payload["site_id"]),
                brief=self.brief,
                actor_key="orchestration-invalid",
            )

    def test_provider_failure_records_generation_failure(self) -> None:
        provider = WebsiteAIProvider(
            chat=lambda **kwargs: (_ for _ in ()).throw(TimeoutError()),
            config=WebsiteProviderSettings(rate_limit=10),
        )
        trace = ActivityTrace()
        with self.assertRaises(WebsiteProviderError):
            orchestrate_generation(
                provider=provider,
                site_id=str(self.payload["site_id"]),
                brief=self.brief,
                actor_key="orchestration-timeout",
                trace=trace,
            )
        self.assertEqual(trace.events[-1].stage, "generation_failed")

    def test_catalog_tool_failure_falls_back_to_sample_data(self) -> None:
        brief = {**self.brief, "use_catalog": True}
        result = orchestrate_generation(
            provider=MockWebsiteAIProvider({"content": json.dumps(self.payload)}),
            site_id=str(self.payload["site_id"]),
            brief=brief,
            actor_key="orchestration-catalog",
            catalog_tool=lambda _: "not records",
        )
        catalog_event = next(event for event in result.activity if event["stage"] == "catalog")
        self.assertEqual(catalog_event["outcome"], "fallback")


class SiteBuilderApiTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="builder-user",
            email="builder@business.example",
            password="test-password",
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={"account_type": "b2b", "role": "distributor", "company_name": "Builder Business"},
        )
        self.other_user = user_model.objects.create_user(
            username="other-user",
            email="other@gmail.com",
            password="test-password",
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.payload = deepcopy(CHEERSTHEPURE_EXAMPLE)

    def post_json(self, path: str, payload: dict):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def post_inquiry(self, payload: dict, key=None, client=None):
        return (client or self.client).post(
            "/api/v1/inquiry/submit/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()),
        )

    def test_builder_landing_route_and_existing_routes_resolve(self) -> None:
        self.client.logout()
        login_response = self.client.get(reverse("site_builder"))
        self.assertRedirects(
            login_response,
            f"{reverse('login')}?next={reverse('site_builder')}",
        )

        self.client.force_login(self.user)
        builder_response = self.client.get(reverse("site_builder"))
        self.assertEqual(builder_response.status_code, 200)
        self.assertContains(builder_response, "SaaSsum AI Builder")
        self.assertContains(builder_response, 'id="saas-workspace"')

        route_names_and_paths = (
            ("index", "/"),
            ("products", "/products/"),
            ("login", "/login/"),
        )
        for route_name, expected_path in route_names_and_paths:
            self.assertEqual(reverse(route_name), expected_path)
            self.assertIsNotNone(resolve(expected_path))

        self.assertEqual(resolve("/api/agent/chat").url_name, "agent_chat_api")
        self.assertEqual(
            resolve("/api/site-builder/business-assistant/").url_name,
            "site_builder_business_assistant",
        )

    @patch("ai_builder.views.dispatch_agent.process_message")
    def test_business_assistant_delegates_to_dispatchai(self, process_message) -> None:
        process_message.return_value = {
            "ok": True,
            "content": "The catalog has current wholesale information.",
            "memories_count": 1,
            "rules_applied": [],
            "decision_type": "product_recommendation",
            "latency_ms": 12,
            "error": False,
        }
        response = self.post_json(
            "/api/site-builder/business-assistant/",
            {"message": "Which products are available?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "The catalog has current wholesale information.")
        self.assertEqual(response.json()["agent_meta"]["memories_count"], 1)
        process_message.assert_called_once()
        self.assertEqual(process_message.call_args.kwargs["user"], self.user)

    def test_business_assistant_rejects_cross_user_session(self) -> None:
        foreign_session = ConversationSession.objects.create(user=self.other_user)
        response = self.post_json(
            "/api/site-builder/business-assistant/",
            {"message": "Check my order", "session_id": str(foreign_session.session_id)},
        )
        self.assertEqual(response.status_code, 404)

    def test_business_assistant_blocks_b2c_accounts(self) -> None:
        b2c = get_user_model().objects.create_user(
                username="builder-b2c",
                email="b2c-builder@gmail.com",
                password="password123",
        )
        UserProfile.objects.create(user=b2c, account_type="b2c", role="customer")
        self.client.force_login(b2c)
        response = self.post_json(
            "/api/site-builder/business-assistant/",
            {"message": "Check my order"},
        )
        self.assertEqual(response.status_code, 403)

    def create_saved_site(self) -> CreatedWebsite:
        response = self.post_json(
            "/api/site-builder/sites/",
            {"site": self.payload, "prompt": "Build a water brand website"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        return CreatedWebsite.objects.get(site_id=response.json()["saved_site"]["site_id"])

    def test_authenticated_user_can_save_and_load_site(self) -> None:
        site = self.create_saved_site()
        response = self.client.get(f"/api/site-builder/sites/{site.site_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["saved_site"]["site"]["site_name"], "CheersThePure")
        self.assertTrue(site.slug.startswith("cheersthepure-"))
        self.assertEqual(site.schema_version, "1.0")
        self.assertEqual(site.revisions.count(), 1)
        self.assertEqual(site.revisions.get().action, WebsiteRevision.Action.GENERATED)

    def test_site_slugs_are_collision_safe(self) -> None:
        first = self.create_saved_site()
        second_payload = deepcopy(self.payload)
        second_payload["site_id"] = str(uuid.uuid4())
        response = self.post_json(
            "/api/site-builder/sites/",
            {"site": second_payload, "prompt": "Build another water brand website"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        second = CreatedWebsite.objects.get(site_id=response.json()["saved_site"]["site_id"])
        self.assertNotEqual(first.slug, second.slug)
        self.assertEqual(second.site_name, first.site_name)

    def test_site_update_creates_immutable_revision_snapshot(self) -> None:
        site = self.create_saved_site()
        updated_payload = deepcopy(self.payload)
        updated_payload["sections"][0]["headline"] = "A revised hydration headline"
        response = self.client.put(
            f"/api/site-builder/sites/{site.site_id}/",
            data=json.dumps({"site": updated_payload}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        revisions = list(site.revisions.order_by("revision_number"))
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0].schema_json["sections"][0]["headline"], self.payload["sections"][0]["headline"])
        self.assertEqual(revisions[1].schema_json["sections"][0]["headline"], "A revised hydration headline")
        self.assertEqual(revisions[1].action, WebsiteRevision.Action.INLINE_EDIT)
        self.assertEqual(revisions[1].schema_version, "1.0")
        revisions[1].metadata = {"tampered": True}
        with self.assertRaises(DjangoValidationError):
            revisions[1].save()

    def test_user_cannot_load_another_users_site(self) -> None:
        site = self.create_saved_site()
        self.client.force_login(self.other_user)
        response = self.client.get(f"/api/site-builder/sites/{site.site_id}/")
        self.assertEqual(response.status_code, 404)

    @override_settings(GROQ_API_KEY="gsk_test_builder")
    @patch("ai_builder.views.groq_client.chat")
    def test_refine_updates_only_selected_section(self, groq_chat) -> None:
        site = self.create_saved_site()
        original_sections = deepcopy(site.schema_json["sections"])
        updated_hero = deepcopy(original_sections[0])
        updated_hero["headline"] = "A fresher way to hydrate"
        groq_chat.return_value = {"content": json.dumps(updated_hero)}

        response = self.post_json(
            "/api/site-builder/refine/",
            {
                "site_id": str(site.site_id),
                "section_id": updated_hero["id"],
                "instruction": "Make the headline punchier.",
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        site.refresh_from_db()
        self.assertEqual(site.schema_json["sections"][0]["headline"], "A fresher way to hydrate")
        self.assertEqual(site.schema_json["sections"][1:], original_sections[1:])

    def test_publish_creates_shareable_public_read_only_site(self) -> None:
        site = self.create_saved_site()
        response = self.client.post(f"/api/site-builder/sites/{site.site_id}/publish/", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 200)
        site.refresh_from_db()
        self.assertTrue(site.is_published)
        shared = Client().get(f"/builder/share/{site.share_token}/")
        self.assertEqual(shared.status_code, 200)
        self.assertContains(shared, "shared-site-root")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_quote_form_creates_pending_request_token_and_dashboard_record(self) -> None:
        key = uuid.uuid4()
        payload = {
            "name": "SaaSsum Integration QA",
            "email": "integration.qa@business.example",
            "company": "Integration QA",
            "capacity": "500 ml",
            "quantity": "250",
            "details": "Clearly identified development verification inquiry",
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_inquiry(payload, key=key)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()["success"])
        self.assertEqual(response.json()["message"], "Quote request received")
        quote = QuoteRequest.objects.get(pk=response.json()["quote_id"])
        self.assertEqual(quote.user, self.user)
        self.assertEqual(quote.name, "SaaSsum Integration QA")
        self.assertEqual(quote.size, "500 ml")
        self.assertEqual(quote.status, "pending")
        self.assertFalse(quote.email_verified)
        self.assertEqual(quote.inquiry_idempotency_key, str(key))
        self.assertTrue(EmailVerificationToken.objects.filter(quote_request=quote).exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/verify-email/", mail.outbox[0].body)
        dashboard = self.client.get("/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Your Wholesale Quotes (1)")
        self.assertContains(dashboard, "500 ml")

    def test_idempotent_retry_returns_same_quote_without_duplicate_token(self) -> None:
        key = uuid.uuid4()
        payload = {
            "name": "Retry Buyer",
            "email": "retry@business.example",
            "company": "Retry Co",
            "size": "1000 ml",
            "quantity": 40,
        }
        first = self.post_inquiry(payload, key=key)
        second = self.post_inquiry(payload, key=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["quote_id"], second.json()["quote_id"])
        self.assertEqual(QuoteRequest.objects.filter(inquiry_idempotency_key=str(key)).count(), 1)
        self.assertEqual(EmailVerificationToken.objects.filter(quote_request_id=first.json()["quote_id"]).count(), 1)

    def test_reusing_idempotency_key_with_different_data_conflicts(self) -> None:
        key = uuid.uuid4()
        first = self.post_inquiry(
            {"name": "First", "email": "first@business.example", "size": "250 ml", "quantity": 10},
            key=key,
        )
        second = self.post_inquiry(
            {"name": "Second", "email": "second@business.example", "size": "250 ml", "quantity": 10},
            key=key,
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(QuoteRequest.objects.filter(inquiry_idempotency_key=str(key)).count(), 1)

    def test_invalid_inquiry_fields_are_rejected(self) -> None:
        invalid_payloads = [
            {"name": "", "email": "valid@business.example", "capacity": "500 ml", "quantity": 1},
            {"name": "Buyer", "email": "invalid", "capacity": "500 ml", "quantity": 1},
            {"name": "Buyer", "email": "valid@business.example", "capacity": "20 L", "quantity": 1},
            {"name": "Buyer", "email": "valid@business.example", "capacity": "500 ml", "quantity": 0},
            {"name": "Buyer", "email": "valid@business.example", "capacity": "500 ml", "quantity": 1_000_001},
            {"name": "Buyer", "email": "valid@business.example", "capacity": "500 ml", "quantity": 1, "unknown": "no"},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                cache.clear()
                response = self.post_inquiry(payload)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["ok"])
        self.assertEqual(QuoteRequest.objects.count(), 0)

    def test_anonymous_and_b2c_users_are_forbidden(self) -> None:
        payload = {"name": "Buyer", "email": "buyer@business.example", "size": "500 ml", "quantity": 1}
        anonymous = Client().post(
            "/api/v1/inquiry/submit/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(anonymous.status_code, 403)
        self.client.force_login(self.other_user)
        b2c = self.post_inquiry(payload)
        self.assertEqual(b2c.status_code, 403)
        self.assertEqual(QuoteRequest.objects.count(), 0)

    def test_endpoint_rejects_wrong_content_type_and_method(self) -> None:
        response = self.client.post("/api/v1/inquiry/submit/", {"name": "Buyer"})
        self.assertEqual(response.status_code, 400)
        response = self.client.get("/api/v1/inquiry/submit/")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "POST")

    def test_endpoint_rejects_missing_idempotency_key_and_oversized_body(self) -> None:
        response = self.client.post(
            "/api/v1/inquiry/submit/",
            data=json.dumps({"name": "Buyer", "email": "buyer@business.example", "size": "500 ml", "quantity": 1}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            "/api/v1/inquiry/submit/",
            data=b" " * 16_385,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(SAASSUM_INQUIRY_API_URL="/configured/inquiry/submit/")
    def test_workspace_uses_server_configured_inquiry_endpoint(self) -> None:
        response = self.client.get("/builder/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-inquiry-url="/configured/inquiry/submit/"')

    def test_endpoint_preserves_csrf_protection(self) -> None:
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            "/api/v1/inquiry/submit/",
            data=json.dumps({"name": "Buyer", "email": "buyer@business.example", "size": "500 ml", "quantity": 1}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 403)

    def test_rate_limit_returns_429_without_creating_more_quotes_than_allowed(self) -> None:
        payload = {"name": "Rate Buyer", "email": "rate@business.example", "size": "500 ml", "quantity": 1}
        responses = [self.post_inquiry(payload) for _ in range(6)]
        self.assertEqual([response.status_code for response in responses], [201] * 5 + [429])
        self.assertEqual(QuoteRequest.objects.count(), 5)
        self.assertEqual(responses[-1]["Retry-After"], "600")

    @patch("ai_builder.views.create_quote_request_workflow", side_effect=RuntimeError("sensitive db detail"))
    def test_persistence_failure_returns_generic_500(self, create_workflow):
        response = self.post_inquiry(
            {"name": "Failure Buyer", "email": "failure@business.example", "size": "500 ml", "quantity": 1}
        )
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("sensitive db detail", response.content.decode())

    def test_client_cannot_claim_trusted_catalog_price(self) -> None:
        product = self.payload["sections"][2]["items"][0]
        product["data_source"] = "cheersthepure_database"
        product["price"] = {
            "amount_minor": 1000,
            "currency": "INR",
            "source": "cheersthepure_database",
        }
        response = self.post_json("/api/site-builder/sites/", {"site": self.payload})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CreatedWebsite.objects.count(), 0)

    def test_client_cannot_mark_sample_testimonial_verified(self) -> None:
        self.payload["sections"].append(
            {
                "id": "testimonials-sample",
                "type": "testimonials",
                "title": "What buyers say",
                "items": [
                    {
                        "quote": "A sample testimonial.",
                        "attribution": "Sample customer",
                        "content_status": "verified",
                    }
                ],
            }
        )
        response = self.post_json("/api/site-builder/sites/", {"site": self.payload})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CreatedWebsite.objects.count(), 0)

    @override_settings(GROQ_API_KEY="gsk_test_builder")
    @patch("ai_builder.views.groq_client.chat")
    def test_generation_cannot_claim_trusted_catalog_price(self, groq_chat) -> None:
        product = self.payload["sections"][2]["items"][0]
        product["data_source"] = "cheersthepure_database"
        product["price"] = {
            "amount_minor": 1000,
            "currency": "INR",
            "source": "cheersthepure_database",
        }
        groq_chat.side_effect = lambda **kwargs: {
            "content": json.dumps(
                {
                    **self.payload,
                    "site_id": json.loads(kwargs["messages"][1]["content"])["site_id"],
                }
            )
        }
        response = self.post_json("/api/site-builder/generate/", {"prompt": "Build a water brand site"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(CreatedWebsite.objects.count(), 0)

    @patch("ai_builder.views.groq_client.chat", side_effect=RuntimeError("not configured"))
    def test_generation_reports_unavailable_without_fake_success(self, groq_chat) -> None:
        response = self.post_json(
            "/api/site-builder/generate/",
            {"prompt": "Build a business website"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(CreatedWebsite.objects.count(), 0)


if __name__ == "__main__":
    unittest.main()
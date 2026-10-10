import unittest
from copy import deepcopy
import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.core import mail
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from pydantic import ValidationError

from app.models import EmailVerificationToken, QuoteRequest, UserProfile

from .schema_examples import CHEERSTHEPURE_EXAMPLE
from .models import CreatedWebsite
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

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _validated_json_object('{"site_name":"first","site_name":"second"}')


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

    def test_user_cannot_load_another_users_site(self) -> None:
        site = self.create_saved_site()
        self.client.force_login(self.other_user)
        response = self.client.get(f"/api/site-builder/sites/{site.site_id}/")
        self.assertEqual(response.status_code, 404)

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
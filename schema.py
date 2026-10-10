from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


Theme = Literal["cyan", "sky", "emerald", "indigo"]
ProductLayout = Literal["cards", "tiers"]
QuoteField = Literal["name", "email", "company", "size", "quantity", "delivery_notes"]


class SiteComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SiteMetadata(SiteComponent):
    site_title: str = Field(min_length=1, max_length=120)
    brand_name: str = Field(min_length=1, max_length=80)
    theme: Theme
    font_family: str = Field(min_length=1, max_length=100)
    logo_text: str = Field(min_length=1, max_length=40)


class CallToAction(SiteComponent):
    label: str = Field(min_length=1, max_length=60)
    link: str = Field(min_length=1, max_length=2048)


class HeroSection(SiteComponent):
    headline: str = Field(min_length=1, max_length=180)
    subheadline: str = Field(min_length=1, max_length=500)
    badge_text: str = Field(min_length=1, max_length=80)
    primary_cta: CallToAction
    secondary_cta: CallToAction


class PurityFeature(SiteComponent):
    icon_key: str = Field(min_length=1, max_length=60, pattern=r"^[a-z][a-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=300)


class PurityFeaturesSection(SiteComponent):
    section_title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(min_length=1, max_length=300)
    features: list[PurityFeature] = Field(min_length=3, max_length=4)


class Product(SiteComponent):
    name: str = Field(min_length=1, max_length=100)
    capacity: str = Field(min_length=1, max_length=40)
    price: Decimal = Field(ge=Decimal("0"))
    description: str = Field(min_length=1, max_length=500)
    badge: str = Field(min_length=1, max_length=60)
    image_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_-]*$")


class ProductGridSection(SiteComponent):
    section_title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(min_length=1, max_length=300)
    layout_style: ProductLayout
    products: list[Product] = Field(min_length=1)


class B2BQuotePortal(SiteComponent):
    section_title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(min_length=1, max_length=300)
    target_api_url: str = Field(min_length=1, max_length=2048)
    submit_button_text: str = Field(min_length=1, max_length=60)
    fields: list[QuoteField] = Field(min_length=6, max_length=6)

    @field_validator("fields")
    @classmethod
    def require_each_quote_field_once(cls, fields: list[QuoteField]) -> list[QuoteField]:
        if len(set(fields)) != 6:
            raise ValueError("fields must include each supported quote field exactly once")
        return fields


class SocialLink(SiteComponent):
    platform: str = Field(min_length=1, max_length=40)
    url: str = Field(min_length=1, max_length=2048)


class SiteFooter(SiteComponent):
    brand_name: str = Field(min_length=1, max_length=80)
    copyright_text: str = Field(min_length=1, max_length=160)
    social_links: list[SocialLink]
    contact_email: EmailStr
    contact_phone: str = Field(default="", max_length=40)


class SiteSchema(SiteComponent):
    metadata: SiteMetadata
    hero: HeroSection
    purity_features: PurityFeaturesSection
    product_grid: ProductGridSection
    b2b_quote_portal: B2BQuotePortal
    footer: SiteFooter
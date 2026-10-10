import json
from typing import Annotated, Literal
from uuid import UUID
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)


ThemeColor = Literal["sky", "cyan", "blue", "emerald", "violet", "slate", "neutral"]
SurfaceMode = Literal["light", "dark"]
BusinessType = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]
SectionId = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")]
IconName = Literal[
    "activity",
    "badge-check",
    "droplet",
    "flask-conical",
    "leaf",
    "package-check",
    "shield-check",
    "sparkles",
    "truck",
    "users",
    "zap",
]
HeroAction = Literal[
    "scroll_to_products",
    "submit_b2b_inquiry",
    "contact_business",
    "learn_more",
]
QuoteFieldName = Literal["name", "email", "company", "capacity", "quantity", "details"]
BindingKey = Literal["product_id", "name", "capacity"]
MAX_SITE_JSON_BYTES = 100_000

_HTML_MARKERS = ("<", ">", "javascript:", "data:text/html", "vbscript:", "@import", "expression(")
_UNSAFE_TEXT_PATTERNS = (
    re.compile(r"\bon[a-z]+\s*=", re.IGNORECASE),
    re.compile(r"\{\{|\{%|<%|<\?"),
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def reject_markup_and_script_strings(self) -> "StrictModel":
        for value in self.__dict__.values():
            if isinstance(value, HttpUrl):
                if value.username or value.password:
                    raise ValueError("URLs containing credentials are not allowed")
                value = str(value)
            if not isinstance(value, str):
                continue
            lowered = value.lower()
            if any(marker in lowered for marker in _HTML_MARKERS) or any(
                pattern.search(value) for pattern in _UNSAFE_TEXT_PATTERNS
            ):
                raise ValueError("markup and executable content are not allowed")
        return self


class Brand(StrictModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    logo_text: Annotated[str, StringConstraints(min_length=1, max_length=40)]


class Theme(StrictModel):
    color: ThemeColor
    surface: SurfaceMode = "light"


class SectionBase(StrictModel):
    id: SectionId
    type: str


class HeroSection(SectionBase):
    type: Literal["hero"]
    headline: Annotated[str, StringConstraints(min_length=1, max_length=180)]
    subheadline: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    cta_text: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    cta_action: HeroAction
    image_url: HttpUrl | None = None
    theme_color: ThemeColor


class FeatureItem(StrictModel):
    icon: IconName
    title: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    description: Annotated[str, StringConstraints(min_length=1, max_length=300)]


class FeaturesSection(SectionBase):
    type: Literal["features"]
    title: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    subtitle: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    items: list[FeatureItem] = Field(min_length=3, max_length=4)


class TrustedPrice(StrictModel):
    amount_minor: int = Field(ge=0, le=999_999_999_999)
    currency: Literal["INR"]
    source: Literal["cheersthepure_database"]


class CatalogBinding(StrictModel):
    source: Literal["cheersthepure_catalog"]
    entity: Literal["product"]
    key: BindingKey
    value: Annotated[str, StringConstraints(min_length=1, max_length=80)]


class ProductItem(StrictModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    capacity: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    description: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    image_url: HttpUrl | None = None
    badge: Annotated[str, StringConstraints(max_length=60)] | None = None
    data_source: Literal["sample", "cheersthepure_database"]
    price: TrustedPrice | None = None
    data_binding: CatalogBinding | None = None

    @model_validator(mode="after")
    def validate_price_provenance(self) -> "ProductItem":
        if self.data_source == "sample" and self.price is not None:
            raise ValueError("sample products cannot include a price")
        if self.data_source == "cheersthepure_database" and self.price is None:
            raise ValueError("database products require a trusted backend price")
        return self


class ProductGridSection(SectionBase):
    type: Literal["product_grid"]
    title: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    items: list[ProductItem] = Field(min_length=1, max_length=12)


class FormField(StrictModel):
    name: QuoteFieldName
    label: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    required: bool = True


class QuoteFormSection(SectionBase):
    type: Literal["quote_form"]
    title: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    subtitle: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    fields: list[FormField] = Field(min_length=1, max_length=6)
    submit_button_text: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    action: Literal["submit_b2b_inquiry"]

    @field_validator("fields")
    @classmethod
    def require_unique_field_names(cls, fields: list[FormField]) -> list[FormField]:
        names = [field.name for field in fields]
        if len(names) != len(set(names)):
            raise ValueError("quote form field names must be unique")
        return fields


class FooterLink(StrictModel):
    label: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    url: str

    @field_validator("url")
    @classmethod
    def validate_link_url(cls, value: str) -> str:
        if value.startswith("/") and not value.startswith("//") and "\\" not in value:
            return value
        try:
            parsed_url = HttpUrl(value)
            if parsed_url.username or parsed_url.password:
                raise ValueError("URLs containing credentials are not allowed")
        except Exception as error:
            raise ValueError("link must be a safe HTTP(S) URL or local absolute path") from error
        return value


class FooterSection(SectionBase):
    type: Literal["footer"]
    company_name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    copyright: Annotated[str, StringConstraints(min_length=1, max_length=180)]
    links: list[FooterLink] = Field(max_length=12)


class TextBlockSection(SectionBase):
    type: Literal["text_block"]
    title: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    body: Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class TestimonialItem(StrictModel):
    quote: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    attribution: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    content_status: Literal["sample", "verified"]


class TestimonialsSection(SectionBase):
    type: Literal["testimonials"]
    title: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    items: list[TestimonialItem] = Field(min_length=1, max_length=8)


SiteSection = Annotated[
    HeroSection
    | FeaturesSection
    | ProductGridSection
    | QuoteFormSection
    | FooterSection
    | TextBlockSection
    | TestimonialsSection,
    Field(discriminator="type"),
]

SECTION_MODELS = {
    "hero": HeroSection,
    "features": FeaturesSection,
    "product_grid": ProductGridSection,
    "quote_form": QuoteFormSection,
    "footer": FooterSection,
    "text_block": TextBlockSection,
    "testimonials": TestimonialsSection,
}


class SiteSchema(StrictModel):
    schema_version: Literal["1.0"]
    site_id: UUID
    site_name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    business_type: BusinessType
    brand: Brand
    theme: Theme
    sections: list[SiteSection] = Field(min_length=1, max_length=12)

    @field_validator("sections")
    @classmethod
    def require_unique_section_ids(cls, sections: list[SiteSection]) -> list[SiteSection]:
        ids = [section.id for section in sections]
        if len(ids) != len(set(ids)):
            raise ValueError("section IDs must be unique")
        return sections

    @model_validator(mode="before")
    @classmethod
    def enforce_document_size(cls, value):
        if isinstance(value, dict):
            try:
                document_size = len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
            except (TypeError, ValueError) as error:
                raise ValueError("site schema must be JSON-serializable") from error
            if document_size > MAX_SITE_JSON_BYTES:
                raise ValueError(f"site schema exceeds the {MAX_SITE_JSON_BYTES}-byte limit")
        return value


QuoteCapacity = Literal["250 ml", "500 ml", "1000 ml", "2 litres"]


class InquirySubmission(StrictModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=150)]
    email: Annotated[EmailStr, Field(max_length=254)]
    company: Annotated[str, StringConstraints(max_length=200)] = ""
    size: QuoteCapacity | None = None
    capacity: QuoteCapacity | None = None
    quantity: int = Field(strict=True, gt=0, le=1_000_000)
    details: Annotated[str, StringConstraints(max_length=2000)] = ""

    @field_validator("quantity", mode="before")
    @classmethod
    def parse_form_quantity(cls, value):
        if isinstance(value, str) and value.isdecimal():
            return int(value)
        return value

    @model_validator(mode="after")
    def require_one_capacity(self) -> "InquirySubmission":
        if not self.size and not self.capacity:
            raise ValueError("Provide size or capacity.")
        if self.size and self.capacity and self.size != self.capacity:
            raise ValueError("size and capacity must match when both are provided.")
        return self

    @property
    def normalized_size(self) -> str:
        return self.size or self.capacity
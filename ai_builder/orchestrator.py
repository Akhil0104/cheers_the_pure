"""Bounded SaaSsum generation orchestration and safe activity tracing."""

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Callable

from .generation import generate_validated_site
from .quality import review_site
from .schemas import SiteSchema

MAX_PROVIDER_CALLS = 3


@dataclass
class ActivityEvent:
    stage: str
    outcome: str
    summary: str
    duration_ms: int | None = None

    def as_dict(self) -> dict:
        result = {
            "stage": self.stage,
            "outcome": self.outcome,
            "summary": self.summary,
        }
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        return result


@dataclass
class ActivityTrace:
    events: list[ActivityEvent] = field(default_factory=list)

    def record(self, stage: str, outcome: str, summary: str, started: float | None = None) -> None:
        duration_ms = None if started is None else round((monotonic() - started) * 1000)
        self.events.append(ActivityEvent(stage, outcome, summary, duration_ms))

    def as_list(self) -> list[dict]:
        return [event.as_dict() for event in self.events]


@dataclass(frozen=True)
class PlannerOutput:
    section_types: tuple[str, ...]
    catalog_required: bool = False


def plan_website(brief: dict) -> PlannerOutput:
    requested = tuple(brief.get("requested_sections") or ())
    defaults = ("hero", "features", "product_grid", "quote_form", "footer")
    sections = tuple(dict.fromkeys((*requested, *defaults)))
    return PlannerOutput(section_types=sections[:12], catalog_required=False)


def retrieve_catalog_records(
    brief: dict,
    *,
    catalog_tool: Callable[[dict], list[dict]] | None = None,
) -> list[dict]:
    """Return trusted records only when an explicitly supplied tool is requested."""
    if not brief.get("use_catalog") or catalog_tool is None:
        return []
    records = catalog_tool(brief)
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise ValueError("Catalog tool returned an invalid record set.")
    return records


@dataclass(frozen=True)
class OrchestrationResult:
    site: SiteSchema
    quality_review: dict
    activity: list[dict]


def orchestrate_generation(
    *,
    provider,
    site_id: str,
    brief: dict,
    actor_key: str,
    trace: ActivityTrace | None = None,
    catalog_tool: Callable[[dict], list[dict]] | None = None,
) -> OrchestrationResult:
    trace = trace or ActivityTrace()
    started = monotonic()
    try:
        plan = plan_website(brief)
        trace.record(
            "planning",
            "succeeded",
            f"Planned {len(plan.section_types)} supported website sections.",
            started,
        )
    except Exception:
        trace.record("planning", "failed", "Website planning could not be completed.", started)
        raise

    if brief.get("use_catalog"):
        started = monotonic()
        try:
            records = retrieve_catalog_records(brief, catalog_tool=catalog_tool)
            trace.record("catalog", "succeeded", f"Retrieved {len(records)} trusted catalog record(s).", started)
        except Exception:
            records = []
            trace.record(
                "catalog",
                "fallback",
                "Trusted catalog data was unavailable; generation will use clearly marked sample data.",
                started,
            )
    else:
        records = []
        trace.record("catalog", "skipped", "No trusted catalog retrieval was requested; sample data remains unpriced.")

    provider_calls = 0
    started = monotonic()
    trace.record("generation", "started", "Generating validated website content.", started)
    try:
        def on_validation_error(label: str) -> None:
            nonlocal provider_calls
            provider_calls += 1
            trace.record("repair", "attempted", "Repairing invalid generated output.")

        generation_brief = {**brief, "trusted_catalog_records": records}
        site = generate_validated_site(
            provider=provider,
            site_id=site_id,
            brief=generation_brief,
            actor_key=actor_key,
            on_validation_error=on_validation_error,
        )
        provider_calls += 1
        if provider_calls > MAX_PROVIDER_CALLS:
            raise RuntimeError("provider call limit exceeded")
        trace.events[-1].duration_ms = round((monotonic() - started) * 1000)
        trace.events[-1].outcome = "succeeded"
        trace.events[-1].summary = "Generated content passed schema validation."
    except Exception:
        trace.record("generation_failed", "failed", "Website generation did not produce valid content.")
        raise

    started = monotonic()
    _, quality_review = review_site(site.model_dump(mode="json"))
    trace.record(
        "validation",
        "succeeded" if quality_review["ok"] else "blocked",
        "Deterministic safety and quality review completed.",
        started,
    )
    if not quality_review["ok"]:
        trace.record("generation_failed", "failed", "The quality gate blocked unsafe website output.")
        raise ValueError("The generated website failed its safety review.")

    trace.record("preview", "succeeded", "Validated website is ready for preview.")
    return OrchestrationResult(site, quality_review, trace.as_list())

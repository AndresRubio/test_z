import html
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.catalog import facets
from app.catalog.models import Variant

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(raw: str | None) -> str:
    """Drop tags, unescape entities, collapse all whitespace runs to one space.

    Tags are removed outright (not replaced with a space): a tag that abuts
    text with no source whitespace (e.g. ``</strong>,``) must not introduce a
    spurious gap. Any real whitespace adjacent to a tag (e.g. the newline
    after ``<br>``) already collapses to a single space via _WS_RE.

    Tag-stripping runs BEFORE entity-unescaping, not after: some catalog text
    encodes literal comparisons as entities (e.g. "&lt;25kg" for "<25kg").
    Unescaping first would turn that into a bare "<" that could then pair
    with an unrelated later ">" (real or decoded) and make the tag regex
    swallow everything in between as a bogus tag — silently destroying real
    content. Stripping tags first avoids that.

    The decoded "<"/">" characters left behind by unescaping (e.g. "<25kg",
    ">40kg") are intentionally preserved in the output: the catalog encodes
    real feeding/size-guidance comparisons this way ("für Hunde &lt;25kg"),
    and by the time unescaping runs, tags are already gone — so any angle
    bracket still present is guaranteed to be legitimate content, never
    markup. Stripping it would corrupt exactly the feeding/suitability text
    consumers rely on.
    """
    if not raw:
        return ""
    without_tags = _TAG_RE.sub("", raw)
    unescaped = html.unescape(without_tags)
    return _WS_RE.sub(" ", unescaped).strip()


@dataclass(frozen=True)
class IngestReport:
    """What ingest did to the raw dataset; logged at startup, asserted in tests."""

    total_records: int
    exact_duplicates_dropped: int
    pet_type_conflicts: int
    ratings_nulled: int
    price_quarantined: int
    variants_kept: int
    out_of_stock: int


def load_catalog(
    path: Path, max_plausible_price: float = 500.0
) -> tuple[list[Variant], IngestReport]:
    raw_records = json.loads(Path(path).read_text(encoding="utf-8"))

    # Policy 3's *report count* is a raw-feed data-quality signal: how many
    # incoming rows carried no rating at all, counted before dedup collapses
    # repeated rows. A duplicate row that is itself unrated still reflects a
    # real "no rating" occurrence in the source feed, so it counts here even
    # though dedup later drops the row itself. (Per-Variant nulling below is
    # unaffected — it is decided per surviving record, independent of this
    # count.) Uses .get() defensively so a malformed row is merely skipped
    # here; it is still reported precisely, by index, in the loop below.
    ratings_nulled = sum(1 for rec in raw_records if rec.get("rating_count") == 0)

    # Policies 1+2: dedup — drop exact copies, keep first on conflict.
    seen: dict[tuple[int, str], dict] = {}
    deduped: list[tuple[int, dict]] = []
    exact_dropped = 0
    conflicts = 0
    for i, rec in enumerate(raw_records):
        key = (rec.get("site_id"), rec.get("variant_id"))
        if key in seen:
            if rec == seen[key]:
                exact_dropped += 1
            else:
                conflicts += 1
                logger.warning(
                    "ingest conflict: variant %s on site %s has a divergent duplicate; "
                    "kept the first record",
                    rec.get("variant_id"),
                    rec.get("site_id"),
                )
            continue
        seen[key] = rec
        deduped.append((i, rec))

    # Policies 3+4+5: rating nulling, in_stock derivation, price quarantine.
    variants: list[Variant] = []
    quarantined = 0
    for i, rec in deduped:
        try:
            unrated = rec["rating_count"] == 0
            product_name = rec["product_name"]
            variant_name = rec["variant_name"]
            summary = strip_html(rec["summary"])
            variant = Variant(
                product_id=rec["product_id"],
                article_id=rec["article_id"],
                variant_id=rec["variant_id"],
                site_id=rec["site_id"],
                locale=rec["locale"],
                pet_type=rec["pet_type"],
                brand=rec["brands"],
                product_name=product_name,
                variant_name=variant_name,
                summary=summary,
                description=strip_html(rec["description"]),
                ingredients=strip_html(rec["ingredients"]),
                feeding_recommendations=strip_html(rec["feeding_recommendations"]),
                price=rec["price"],
                currency=rec["currency"],
                discount_label=rec["discount_label"],
                rating_average=None if unrated else rec["rating_average"],
                rating_count=rec["rating_count"],
                in_stock=rec["stock_units"] > 0,
                food_form=facets.classify_food_form(product_name, variant_name, summary),
            )
        except (KeyError, TypeError, ValidationError) as exc:
            raise ValueError(f"Malformed catalog record at index {i}: {exc}") from exc
        if variant.price >= max_plausible_price:
            quarantined += 1
            logger.warning(
                "ingest quarantine: variant %s (%s) price %.2f %s fails plausibility cap %.2f",
                variant.variant_id,
                variant.product_name,
                variant.price,
                variant.currency,
                max_plausible_price,
            )
            continue
        variants.append(variant)

    report = IngestReport(
        total_records=len(raw_records),
        exact_duplicates_dropped=exact_dropped,
        pet_type_conflicts=conflicts,
        ratings_nulled=ratings_nulled,
        price_quarantined=quarantined,
        variants_kept=len(variants),
        out_of_stock=sum(1 for v in variants if not v.in_stock),
    )
    logger.info("ingest report: %s", report)
    return variants, report

import json
import re

import pytest

from app.catalog.ingest import load_catalog, strip_html
from tests.conftest import DATASET_PATH


def _record(**overrides):
    base = dict(
        product_id=1, article_id=10, variant_id="1.0", site_id=1, locale="de-DE",
        pet_type="DOGS", brands="TestBrand", product_name="Test Product",
        variant_name="1kg", summary="plain", description="plain", ingredients="",
        feeding_recommendations="", price=9.99, currency="EUR", discount_label=None,
        rating_average=4.5, rating_count=10, stock_units=5, margin_pct=10.0,
        monthly_sales_units=1, revenue_last_30d=1.0,
    )
    base.update(overrides)
    return base


def _load(tmp_path, records, **kwargs):
    path = tmp_path / "cat.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return load_catalog(path, **kwargs)


def test_strip_html_removes_tags_entities_and_collapses_whitespace():
    raw = "Robuster <strong>Ball</strong>,&nbsp;für Wurf- &amp; Apportierspiele<br>\n<ul><li>Item</li></ul>"
    assert strip_html(raw) == "Robuster Ball, für Wurf- & Apportierspiele Item"


def test_strip_html_handles_empty_and_none():
    assert strip_html("") == ""
    assert strip_html(None) == ""


def test_strip_html_preserves_comparison_operators_as_content():
    # Real catalog encodes "<25kg" as the entity &lt;25kg inside markup.
    # Tags must go; the decoded comparison operator is real content and stays.
    assert strip_html("<p>Für Hunde &lt;25&nbsp;kg geeignet</p>") == "Für Hunde <25 kg geeignet"
    assert strip_html("Hunde &gt;40 kg") == "Hunde >40 kg"


def test_cleans_and_maps_fields(tmp_path):
    variants, _ = _load(tmp_path, [_record(summary="<b>Hi</b> &amp; bye", discount_label="-20%")])
    v = variants[0]
    assert v.summary == "Hi & bye"
    assert v.brand == "TestBrand"
    assert v.discount_label == "-20%"
    assert v.in_stock is True
    assert not hasattr(v, "stock_units")
    assert not hasattr(v, "margin_pct")


def test_drops_exact_duplicates(tmp_path):
    variants, report = _load(tmp_path, [_record(), _record(), _record(site_id=3, locale="en-GB")])
    assert len(variants) == 2  # duplicate (site 1, "1.0") dropped, site-3 twin kept
    assert report.exact_duplicates_dropped == 1
    assert report.pet_type_conflicts == 0


def test_conflicting_duplicate_keeps_first_and_counts(tmp_path):
    variants, report = _load(tmp_path, [_record(pet_type="DOGS"), _record(pet_type="CATS")])
    assert len(variants) == 1
    assert variants[0].pet_type == "DOGS"
    assert report.pet_type_conflicts == 1
    assert report.exact_duplicates_dropped == 0


def test_nulls_rating_when_rating_count_zero(tmp_path):
    variants, report = _load(tmp_path, [_record(rating_average=0.0, rating_count=0)])
    assert variants[0].rating_average is None
    assert variants[0].rating_count == 0
    assert report.ratings_nulled == 1


def test_derives_in_stock_boolean(tmp_path):
    variants, report = _load(
        tmp_path, [_record(stock_units=0), _record(variant_id="2.0", stock_units=3)]
    )
    assert [v.in_stock for v in variants] == [False, True]
    assert report.out_of_stock == 1


def test_quarantines_implausible_prices(tmp_path):
    variants, report = _load(
        tmp_path, [_record(price=950.0), _record(variant_id="2.0", price=49.0)]
    )
    assert [v.variant_id for v in variants] == ["2.0"]
    assert report.price_quarantined == 1


def test_quarantine_threshold_is_configurable(tmp_path):
    variants, report = _load(tmp_path, [_record(price=40.0)], max_plausible_price=30.0)
    assert variants == []
    assert report.price_quarantined == 1


def test_raises_on_malformed_record(tmp_path):
    bad = _record()
    del bad["product_name"]
    with pytest.raises(ValueError, match="index 0"):
        _load(tmp_path, [bad])


def test_real_dataset_counts_match_the_known_traps():
    variants, report = load_catalog(DATASET_PATH)
    assert report.total_records == 300
    assert report.exact_duplicates_dropped == 12
    assert report.pet_type_conflicts == 1
    assert report.ratings_nulled == 198   # raw-feed rows with rating_count==0 (issue 02); post-dedup that subset is 192
    assert report.price_quarantined == 24
    assert report.variants_kept == 263 == len(variants)
    assert report.out_of_stock == 8
    assert {v.site_id for v in variants} == {1, 3, 15}
    tag_re = re.compile(r"<[a-zA-Z/][^>]*>")
    for v in variants:
        for field in (v.summary, v.description, v.ingredients, v.feeding_recommendations):
            assert not tag_re.search(field), f"HTML tag leaked into {v.variant_id}: {field!r}"
    assert max(v.price for v in variants) < 500.0
    assert sum(1 for v in variants if v.rating_average is None) == 174  # kept variants unrated: 192 post-dedup minus 18 that were also quarantined

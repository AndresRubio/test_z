"""Shared test doubles and factories. Grows as tasks add make_variant / FakeLLM."""


def make_variant(**overrides):
    from app.catalog.models import Variant

    base = dict(
        product_id=1, article_id=10, variant_id="1.0", site_id=1, locale="de-DE",
        pet_type="DOGS", brand="TestBrand", product_name="Test Product",
        variant_name="1kg", summary="A summary", description="A description",
        ingredients="", feeding_recommendations="", price=9.99, currency="EUR",
        discount_label=None, rating_average=4.5, rating_count=10, in_stock=True,
    )
    base.update(overrides)
    return Variant(**base)

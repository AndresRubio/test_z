from pydantic import BaseModel, ConfigDict


class Site(BaseModel):
    """One shop of the multi-shop platform; fixes catalog subset, locale, currency."""

    model_config = ConfigDict(frozen=True)

    site_id: int
    locale: str
    currency: str


class Variant(BaseModel):
    """One purchasable catalog Variant, already cleaned at ingest: HTML stripped,
    rating nulled when unrated, stock reduced to a boolean.

    Internal Fields (margin_pct, monthly_sales_units, revenue_last_30d, raw
    stock_units) are never parsed — excluded from the API by construction."""

    model_config = ConfigDict(frozen=True)

    product_id: int
    article_id: int
    variant_id: str
    site_id: int
    locale: str
    pet_type: str
    brand: str
    product_name: str
    variant_name: str
    summary: str
    description: str
    ingredients: str
    feeding_recommendations: str
    price: float
    currency: str
    discount_label: str | None
    rating_average: float | None
    rating_count: int
    in_stock: bool

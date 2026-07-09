# Assistant

A chatbot API that helps customers of a multi-shop pet-supplies platform find products, grounded exclusively in a per-site product catalog.

## Language

### Catalog

**Site**:
One shop of the multi-shop platform, identified by `site_id`. A Site determines the catalog subset, the content language, and the currency; catalogs of different Sites are disjoint.
_Avoid_: market, shop (in code), store

**Product**:
The marketing-level entity a customer thinks of (e.g. "Chuckit! Ultra Squeaker Ball"), identified by `product_id`. A Product groups one or more Variants.

**Variant**:
The purchasable unit of a Product — a specific size/flavor/pack (e.g. "Größe L: Ø 7,6 cm"), identified by `variant_id` (and 1:1 by `article_id`). One catalog record = one Variant on one Site.
_Avoid_: article (use only when quoting the dataset's `article_id`), SKU, item

**Pet Type**:
The species a Variant is intended for (`DOGS`, `CATS`).
_Avoid_: category, animal

**Internal Fields**:
Catalog fields that exist for business operations, not customers: `margin_pct`, `monthly_sales_units`, `revenue_last_30d`, raw `stock_units`. They must never appear in an API response.

### Pipeline

**Judge**:
The first pipeline stage: a prompt-only topicality check on a tiny model that decides whether a query is about pet products. Off-topic queries get a polite decline and never reach retrieval.
_Avoid_: classifier, filter, moderator

**Retriever**:
The stage that returns candidate Variants for a query within one Site. The PoC binds a BM25 implementation; the interface is the seam for vector/hybrid/reranker successors.

**Product Card**:
The curated, customer-safe representation of a retrieved Variant returned in `retrieved_products`. Contains only customer-facing fields; unrated Variants show a null rating.
_Avoid_: raw record, row, DTO (in prose)

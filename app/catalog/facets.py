"""Structured retrieval facets derived from otherwise free-text catalog fields.

BM25 is a bag of words: it cannot tell that ``pet_type`` is authoritative or
that "dry" vs "wet" is a hard product distinction — it just weighs term overlap,
so a "dogs" query can surface cats and a "wet food" query can surface dry food.
These helpers recover two structured facets the retriever can act on:

* ``pet_type`` — already clean in the data (``DOGS``/``CATS``); we only need to
  read the *query's* intent so retrieval can hard-filter to that species.
* ``food_form`` — never a field at all; we classify each Variant as ``DRY`` /
  ``WET`` / unknown from high-precision, multilingual name cues, and read the
  same intent from the query so retrieval can boost the matching form.

Vocabulary is multilingual (de/en/es) because each Site speaks one language and
queries arrive in any of them.
"""

# TO_IMPROVE — query understanding stops at these two facets. Everything else a
# shopper says (life-stage puppy/kitten/senior, breed/size band, weight,
# budget/price ceiling, brand as a filter, dietary & health needs like
# grain-free or sensitive-stomach, pack size) is left to raw BM25 term overlap.
# Options: extend these high-precision keyword lists (cheap, more maintenance),
# or add an LLM slot-extraction step that fills a typed intent object (richer,
# one extra model call). Only slots backed by an authoritative clean field
# should hard-filter; derived ones should soft-boost, as food_form does.
# See docs/specs/conversation/
# 2026-07-11-conversational-improvements-design.md § Entity identification.

DOGS = "DOGS"
CATS = "CATS"
DRY = "DRY"
WET = "WET"

# Query-side pet words. Substring match on tokens is enough here; German
# compounds ("Hundefutter") and plurals are covered by prefix membership below.
_DOG_WORDS = ("dog", "hund", "rüde", "perro", "perra")
_CAT_WORDS = ("cat", "katze", "katz", "gato", "gata", "chat")

# Food-form cues. DRY/WET compounds plus wet-packaging forms; deliberately
# high-precision (no bare "dry"/"nass"/"seco", which also hit grooming/coat
# text) so a Variant is only labelled when the signal is unambiguous.
_DRY_CUES = ("trockenfutter", "dry food", "pienso seco", "kibble", "crocchette", "croquetas")
_WET_CUES = (
    "nassfutter", "wet food", "comida húmeda", "comida humeda", "feuchtnahrung",
    "in gelee", "in soße", "in sosse", "in sauce", "in salsa", "en salsa",
    "en gelatina", "in gelatina", "paté", "mousse", "terrine", "filet in",
    "loaf", "jelly", "gravy",
)
# Query-side food-form words: shorter, because a searcher types "wet"/"dry", not
# "nassfutter". These are matched against query tokens/text.
_DRY_QUERY = (*_DRY_CUES, "dry", "trocken", "seco", "seca")
_WET_QUERY = (*_WET_CUES, "wet", "nass", "húmeda", "humeda", "húmedo", "humedo", "mojada")


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(n in text for n in needles)


def detect_pet_type(query: str) -> str | None:
    """The pet species a query is asking for, or None if it does not say."""
    q = query.lower()
    dog = _contains_any(q, _DOG_WORDS)
    cat = _contains_any(q, _CAT_WORDS)
    if dog == cat:  # neither, or ambiguously both -> no constraint
        return None
    return DOGS if dog else CATS


def detect_food_form(query: str) -> str | None:
    """The food form (DRY/WET) a query is asking for, or None if it does not say."""
    q = query.lower()
    dry = _contains_any(q, _DRY_QUERY)
    wet = _contains_any(q, _WET_QUERY)
    if dry == wet:
        return None
    return DRY if dry else WET


def classify_food_form(product_name: str, variant_name: str, summary: str) -> str | None:
    """Label a Variant DRY/WET from its name and summary, or None if unclear.

    Only name/variant/summary are read — never the description, which routinely
    cross-references the other form ("a great complement to dry food") and would
    poison the label. When both forms appear even here, we abstain (None) rather
    than guess: an unlabelled Variant is simply never boosted, which is safe.
    """
    text = f" {product_name} {variant_name} {summary} ".lower()
    dry = _contains_any(text, _DRY_CUES)
    wet = _contains_any(text, _WET_CUES)
    if dry == wet:
        return None
    return DRY if dry else WET

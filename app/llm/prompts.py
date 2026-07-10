from app.retrieval.base import ScoredVariant

LANGUAGE_NAMES = {"de-DE": "German", "en-GB": "English", "es-ES": "Spanish"}

JUDGE_SYSTEM = """\
You decide whether a customer message can be answered from a pet-supplies
product catalog (products and their attributes: prices, availability, brands,
ingredients, feeding recommendations, suitability for a pet).
On-topic: questions about pet products or shopping for pets.
Off-topic: everything else — including general pet trivia with no product
angle (e.g. "Do dogs dream?"), weather, news, sports, coding, chit-chat.

Examples:
Customer message: comida para gatos esterilizados
{"on_topic": true}
Customer message: algo para el mal aliento de mi perro
{"on_topic": true}
Customer message: ¿qué tiempo hace hoy?
{"on_topic": false}
Customer message: ¿los perros sueñan?
{"on_topic": false}

A request to buy, find, or get a recommendation for a pet product — food, toy,
accessory, grooming or care item — is on-topic, in any language and even when
phrased indirectly as a need. Off-topic stays off-topic: weather, news, sport,
chit-chat, and pet trivia with no product angle. Make the JSON verdict match
this rule.
Respond with JSON only: {"on_topic": true} or {"on_topic": false}"""

GENERATION_SYSTEM_TEMPLATE = """\
You are the shopping assistant for an online pet supplies shop.
Answer the customer's question using ONLY the product information provided.
Rules:
- Write your answer in {language}, regardless of the language of the question.
- Recommend specific products by name; mention price (with currency) and availability.
- If a product is out of stock, say so and prefer in-stock alternatives.
- If the provided products do not answer the question, say honestly that this \
shop has no matching product.
- Never invent products, prices, or facts. Be concise and helpful."""

# Static per-Site-locale answers: off-topic declines and no-match answers never
# spend an LLM call (PRD story 12 — off-topic queries waste no compute).
DECLINES = {
    "de-DE": (
        "Ich kann nur Fragen zu Haustierprodukten beantworten. Fragen Sie mich "
        "gerne nach Futter, Spielzeug oder Zubehör für Ihr Haustier!"
    ),
    "en-GB": (
        "I can only help with questions about pet products. Feel free to ask me "
        "about food, toys, or supplies for your pet!"
    ),
    "es-ES": (
        "Solo puedo ayudarte con preguntas sobre productos para mascotas. "
        "¡Pregúntame por comida, juguetes o accesorios para tu mascota!"
    ),
}

NO_MATCH_ANSWERS = {
    "de-DE": (
        "Leider habe ich in diesem Shop kein passendes Produkt zu Ihrer Anfrage "
        "gefunden. Möchten Sie es anders beschreiben oder nach einem anderen "
        "Haustierprodukt fragen?"
    ),
    "en-GB": (
        "I couldn't find a matching product in this shop for your request. Could "
        "you describe it differently, or ask about another pet product?"
    ),
    "es-ES": (
        "No he encontrado ningún producto en esta tienda que coincida con tu "
        "búsqueda. ¿Puedes describirlo de otra forma o preguntar por otro "
        "producto para mascotas?"
    ),
}


def judge_user_prompt(query: str) -> str:
    return f"Customer message: {query}"


def generation_system(locale: str) -> str:
    return GENERATION_SYSTEM_TEMPLATE.format(language=LANGUAGE_NAMES[locale])


def generation_user_prompt(query: str, context: str) -> str:
    return f"Customer question: {query}\n\nAvailable products:\n\n{context}"


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def render_product_context(candidates: list[ScoredVariant], max_chars: int) -> str:
    blocks = []
    for i, scored in enumerate(candidates, 1):
        v = scored.variant
        stock = "In stock" if v.in_stock else "OUT OF STOCK"
        price = f"{v.price:.2f} {v.currency}"
        if v.discount_label:
            price += f" ({v.discount_label})"
        rating = (
            f"{v.rating_average:.1f} ({v.rating_count} reviews)"
            if v.rating_average is not None
            else "No ratings yet"
        )
        details = _truncate(f"{v.summary} {v.description}".strip(), max_chars)
        lines = [
            f"Product {i}: {v.product_name} — {v.variant_name}",
            f"Brand: {v.brand} | For: {v.pet_type} | Price: {price}",
            f"Rating: {rating} | {stock}",
            f"Details: {details}",
        ]
        if v.ingredients:
            lines.append(f"Ingredients: {_truncate(v.ingredients, max_chars)}")
        if v.feeding_recommendations:
            lines.append(f"Feeding: {_truncate(v.feeding_recommendations, max_chars)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)

"""Shared test doubles and factories. Grows as tasks add make_variant / FakeLLM."""


def make_variant(**overrides):
    from app.catalog.models import Variant

    base = dict(
        product_id=1,
        article_id=10,
        variant_id="1.0",
        site_id=1,
        locale="de-DE",
        pet_type="DOGS",
        brand="TestBrand",
        product_name="Test Product",
        variant_name="1kg",
        summary="A summary",
        description="A description",
        ingredients="",
        feeding_recommendations="",
        price=9.99,
        currency="EUR",
        discount_label=None,
        rating_average=4.5,
        rating_count=10,
        in_stock=True,
    )
    base.update(overrides)
    return Variant(**base)


class FakeLLM:
    """Duck-typed OllamaClient for tests: queued responses, call recording."""

    def __init__(self, responses=None, error=None, deltas=None, stream_error=None):
        self.responses = list(responses or [])
        self.error = error
        self.deltas = list(deltas or [])
        self.stream_error = stream_error
        self.calls = []

    async def chat(self, model, system, user, *, temperature=0.0, json_mode=False):
        self.calls.append(
            {
                "model": model,
                "system": system,
                "user": user,
                "temperature": temperature,
                "json_mode": json_mode,
            }
        )
        if self.error is not None:
            raise self.error
        return self.responses.pop(0)

    async def chat_stream(self, model, system, user, *, temperature=0.0):
        self.calls.append(
            {
                "model": model,
                "system": system,
                "user": user,
                "temperature": temperature,
                "streaming": True,
            }
        )
        if self.error is not None:
            raise self.error
        for delta in self.deltas:
            yield delta
        if self.stream_error is not None:
            raise self.stream_error

    async def is_reachable(self):
        return self.error is None

    async def aclose(self):
        pass


class FakeEmbedder:
    """Deterministic, fully offline Embedder double: projects text onto synonym axes.

    Vector dimension i counts occurrences of any term in ``axes[i]``, so cosine
    similarity means "shares concepts" — tests can stage paraphrase matches BM25
    cannot see (kidney ~ renal) without any model download. Every encode() call
    is recorded so caching behaviour is observable.
    """

    def __init__(self, axes=()):
        self.axes = tuple(tuple(term.lower() for term in group) for group in axes)
        self.calls = []

    def encode(self, texts):
        self.calls.append(list(texts))
        return [self._vector(text) for text in texts]

    def _vector(self, text):
        lowered = text.lower()
        return [float(sum(lowered.count(term) for term in group)) for group in self.axes]

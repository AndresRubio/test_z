class LLMUnavailableError(RuntimeError):
    """The Ollama backend could not be reached or returned an error."""


class UnknownSiteError(ValueError):
    """The requested site_id does not exist in the catalog."""

    def __init__(self, site_id: int, valid_sites: list[int]):
        self.site_id = site_id
        self.valid_sites = valid_sites
        super().__init__(f"Unknown site_id {site_id}. Valid sites: {valid_sites}")

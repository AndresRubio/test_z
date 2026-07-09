import pytest

from app.core.errors import LLMUnavailableError, UnknownSiteError


def test_unknown_site_error_names_valid_sites():
    exc = UnknownSiteError(99, [1, 3, 15])
    assert exc.site_id == 99
    assert exc.valid_sites == [1, 3, 15]
    assert "99" in str(exc) and "[1, 3, 15]" in str(exc)


def test_error_hierarchy():
    assert issubclass(LLMUnavailableError, RuntimeError)
    with pytest.raises(ValueError):
        raise UnknownSiteError(2, [1])

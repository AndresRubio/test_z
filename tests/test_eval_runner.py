import pytest

from evals.run_eval import evaluate_case


def _response(product_ids):
    return {
        "answer": "x",
        "retrieved_products": {
            "products": [{"product_id": pid} for pid in product_ids],
            "count": len(product_ids),
        },
    }


def test_products_case_passes_on_any_match():
    case = {"expect": {"kind": "products", "any_of_product_ids": [1, 2]}}
    ok, _ = evaluate_case(case, _response([2, 99]))
    assert ok is True


def test_products_case_fails_without_match():
    case = {"expect": {"kind": "products", "any_of_product_ids": [1]}}
    ok, detail = evaluate_case(case, _response([5]))
    assert ok is False
    assert "1" in detail


def test_empty_products_case():
    case = {"expect": {"kind": "empty_products"}}
    assert evaluate_case(case, _response([]))[0] is True
    assert evaluate_case(case, _response([7]))[0] is False


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        evaluate_case({"expect": {"kind": "banana"}}, _response([]))

import logging

from app.chat.judge import Judge
from app.core.errors import LLMUnavailableError
from tests.helpers import FakeLLM


async def test_on_topic_verdict():
    llm = FakeLLM(responses=['{"on_topic": true}'])
    assert await Judge(llm, "gemma4:e2b").is_on_topic("dry food for my puppy?") is True
    call = llm.calls[0]
    assert call["model"] == "gemma4:e2b"
    assert call["json_mode"] is True
    assert call["temperature"] == 0.0


async def test_off_topic_verdict():
    llm = FakeLLM(responses=['{"on_topic": false}'])
    assert await Judge(llm, "m").is_on_topic("What's the weather today?") is False


async def test_unparseable_verdict_fails_open_with_warning(caplog):
    llm = FakeLLM(responses=["not json at all"])
    with caplog.at_level(logging.WARNING):
        assert await Judge(llm, "m").is_on_topic("anything") is True
    assert any("failing open" in r.getMessage() for r in caplog.records)


async def test_non_bool_verdict_fails_open():
    llm = FakeLLM(responses=['{"on_topic": "maybe"}'])
    assert await Judge(llm, "m").is_on_topic("anything") is True


async def test_missing_key_fails_open():
    llm = FakeLLM(responses=['{"verdict": true}'])
    assert await Judge(llm, "m").is_on_topic("anything") is True


async def test_non_object_json_fails_open():
    llm = FakeLLM(responses=['"just a string"'])  # valid JSON, but not an object
    assert await Judge(llm, "m").is_on_topic("anything") is True


async def test_none_content_fails_open():
    # Ollama can return {"message": {"content": null}} -> chat() yields None;
    # json.loads(None) raises TypeError, which must still fail open.
    llm = FakeLLM(responses=[None])
    assert await Judge(llm, "m").is_on_topic("anything") is True


async def test_llm_error_fails_open_with_warning(caplog):
    llm = FakeLLM(error=LLMUnavailableError("down"))
    with caplog.at_level(logging.WARNING):
        assert await Judge(llm, "m").is_on_topic("anything") is True
    assert any("failing open" in r.getMessage() for r in caplog.records)


async def test_verdict_generation_is_capped_by_num_predict():
    llm = FakeLLM(responses=['{"on_topic": true}'])
    await Judge(llm, "gemma4:e2b", num_predict=16).is_on_topic("dog food?")
    assert llm.calls[0]["num_predict"] == 16


async def test_num_predict_default_matches_settings_default():
    from app.core.config import Settings

    llm = FakeLLM(responses=['{"on_topic": true}'])
    await Judge(llm, "m").is_on_topic("dog food?")
    assert llm.calls[0]["num_predict"] == Settings(_env_file=None).judge_num_predict

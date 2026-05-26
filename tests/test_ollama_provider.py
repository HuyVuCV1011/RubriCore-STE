from __future__ import annotations

import json

import httpx
import pytest

from app.ai.ollama import OllamaGradingProvider, OllamaProviderError


class SettingsStub:
    ollama_model = "local-model"
    ollama_base_url = "http://localhost:11434/"
    ollama_timeout_seconds = 42.0


def test_ollama_provider_can_be_created_from_settings() -> None:
    provider = OllamaGradingProvider.from_settings(SettingsStub())

    assert provider.model_name == "local-model"
    assert provider.base_url == "http://localhost:11434"
    assert provider.timeout_seconds == 42.0


def test_ollama_provider_posts_structured_chat_request_and_returns_json_content() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        body = json.loads(request.content)
        captured["body"] = body
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "criterion_suggestions": [
                                {
                                    "criterion_key": "correctness",
                                    "score": "2",
                                    "confidence": "0.86",
                                    "explanation": "The answer matches the expected behavior.",
                                    "evidence_references": ["evidence-1"],
                                }
                            ],
                            "confidence": "0.86",
                        }
                    )
                },
                "done": True,
            },
        )

    client = httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(handler))
    provider = OllamaGradingProvider(model_name="llama3.2:1b", client=client)

    output = provider.evaluate({"rubric_schema": {"criteria": [{"key": "correctness"}]}, "evidence": []})

    assert captured["path"] == "/api/chat"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "llama3.2:1b"
    assert body["format"]["type"] == "object"
    assert "criterion_suggestions" in body["format"]["required"]
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0}
    assert output["criterion_suggestions"][0]["criterion_key"] == "correctness"
    assert output["confidence"] == "0.86"


def test_ollama_provider_rejects_non_json_message_content() -> None:
    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"message": {"content": "not json"}, "done": True})
        ),
    )
    provider = OllamaGradingProvider(client=client)

    with pytest.raises(OllamaProviderError, match="not valid JSON"):
        provider.evaluate({"rubric_schema": {}, "evidence": []})


def test_ollama_provider_repairs_common_local_model_contract_drift() -> None:
    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {
                                "criterion_suggestions": [
                                    {
                                        "criterion_key": "correctness",
                                        "score": "meets",
                                        "confidence": "high",
                                        "explanation": "Meets the target behavior.",
                                        "evidence_references": ["not-an-evidence-id"],
                                    }
                                ],
                                "confidence": "medium",
                            }
                        )
                    },
                    "done": True,
                },
            )
        ),
    )
    provider = OllamaGradingProvider(client=client)

    output = provider.evaluate(
        {
            "rubric_schema": {
                "criteria": [{"key": "correctness", "weight": "2"}],
                "performance_levels": [{"key": "meets", "score": "2"}],
            },
            "evidence": [{"id": "evidence-1"}],
        }
    )

    assert output["confidence"] == "0.75"
    assert output["criterion_suggestions"][0]["score"] == "4.0"
    assert output["criterion_suggestions"][0]["confidence"] == "0.90"
    assert output["criterion_suggestions"][0]["evidence_references"] == ["evidence-1"]

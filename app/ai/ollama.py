from __future__ import annotations

import json
from typing import Any

import httpx


DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2:1b"
DEFAULT_TIMEOUT_SECONDS = 120.0


class OllamaProviderError(RuntimeError):
    """Raised when Ollama does not return a usable structured grading payload."""


class OllamaGradingProvider:
    provider_name = "ollama"

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_OLLAMA_MODEL,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    @classmethod
    def from_settings(cls, settings: Any) -> OllamaGradingProvider:
        return cls(
            model_name=settings.ollama_model,
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
        )

    def evaluate(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model_name,
            "messages": _messages_for_grading(request_payload),
            "format": _grading_output_json_schema(),
            "stream": False,
            "options": {"temperature": 0},
        }
        response_payload = self._post_chat(payload)
        content = _message_content(response_payload)
        return _normalize_local_grading_payload(_parse_json_object(content), request_payload)

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._client
        if client is not None:
            response = client.post("/api/chat", json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            return _response_json(response)

        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as owned_client:
            response = owned_client.post("/api/chat", json=payload)
            response.raise_for_status()
            return _response_json(response)


def _messages_for_grading(request_payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a grading assistant for RubriCore-STE. Return only one valid JSON object. "
                "Do not include markdown, prose outside JSON, or hidden reasoning. "
                "Use only the submitted evidence and rubric in the request. "
                "Every criterion suggestion must include criterion_key, score, confidence, explanation, "
                "and evidence_references using evidence IDs from the request. "
                "Scores must stay within each criterion's rubric maximum. "
                "The root object must include criterion_suggestions and confidence."
            ),
        },
        {
            "role": "user",
            "content": (
                "Evaluate the submitted evidence against the rubric. "
                "Return a grading JSON object for this exact request. "
                "Do not repeat the request. "
                "For each rubric criterion, create one criterion_suggestions item. "
                "Use the evidence id values exactly as provided.\n\n"
                f"REQUEST_JSON:\n{json.dumps(request_payload, sort_keys=True, default=str)}"
            ),
        },
    ]


def _grading_output_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
        "required": ["criterion_suggestions", "confidence"],
        "properties": {
            "criterion_suggestions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["criterion_key", "score", "confidence", "explanation", "evidence_references"],
                    "properties": {
                        "criterion_key": {"type": "string"},
                        "score": {"type": ["number", "string"]},
                        "confidence": {"type": ["number", "string"]},
                        "explanation": {"type": "string"},
                        "evidence_references": {"type": "array", "items": {"type": "string"}},
                        "ambiguity_flags": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "confidence": {"type": ["number", "string"]},
            "overall_feedback_draft": {"type": "string"},
            "uncertainty_reasons": {"type": "array", "items": {"type": "string"}},
            "evidence_references": {"type": "array", "items": {"type": "string"}},
            "policy_flags": {"type": "array", "items": {"type": "string"}},
        },
    }


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise OllamaProviderError("Ollama response was not JSON.") from exc
    if not isinstance(payload, dict):
        raise OllamaProviderError("Ollama response must be a JSON object.")
    return payload


def _message_content(response_payload: dict[str, Any]) -> str:
    message = response_payload.get("message")
    if not isinstance(message, dict):
        raise OllamaProviderError("Ollama response did not include a message object.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OllamaProviderError("Ollama response did not include message content.")
    return content


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except ValueError as exc:
        raise OllamaProviderError("Ollama message content was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise OllamaProviderError("Ollama grading content must be a JSON object.")
    return payload


def _normalize_local_grading_payload(payload: dict[str, Any], request_payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    level_scores = _performance_level_scores(request_payload)
    criterion_weights = _criterion_weights(request_payload)
    evidence_ids = _evidence_ids(request_payload)
    normalized["confidence"] = _normalize_confidence(normalized.get("confidence"))

    suggestions = normalized.get("criterion_suggestions")
    if not isinstance(suggestions, list):
        return normalized

    normalized_suggestions: list[Any] = []
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            normalized_suggestions.append(suggestion)
            continue

        item = dict(suggestion)
        criterion_key = item.get("criterion_key")
        if isinstance(criterion_key, str):
            item["score"] = _normalize_score(
                item.get("score"),
                level_scores=level_scores,
                criterion_weight=criterion_weights.get(criterion_key, 1.0),
            )
        item["confidence"] = _normalize_confidence(item.get("confidence"))
        item["evidence_references"] = _normalize_evidence_references(
            item.get("evidence_references"),
            allowed_ids=evidence_ids,
        )
        normalized_suggestions.append(item)

    normalized["criterion_suggestions"] = normalized_suggestions
    return normalized


def _performance_level_scores(request_payload: dict[str, Any]) -> dict[str, float]:
    rubric_schema = request_payload.get("rubric_schema")
    if not isinstance(rubric_schema, dict):
        return {}
    levels = rubric_schema.get("performance_levels")
    if not isinstance(levels, list):
        return {}

    scores: dict[str, float] = {}
    for level in levels:
        if not isinstance(level, dict):
            continue
        key = level.get("key")
        if not isinstance(key, str):
            continue
        score = level.get("score")
        if score is None:
            continue
        try:
            scores[key] = float(score)
        except (TypeError, ValueError):
            continue
    return scores


def _criterion_weights(request_payload: dict[str, Any]) -> dict[str, float]:
    rubric_schema = request_payload.get("rubric_schema")
    if not isinstance(rubric_schema, dict):
        return {}
    criteria = rubric_schema.get("criteria")
    if not isinstance(criteria, list):
        return {}

    weights: dict[str, float] = {}
    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        key = criterion.get("key")
        if not isinstance(key, str):
            continue
        try:
            weights[key] = float(criterion.get("weight", 1))
        except (TypeError, ValueError):
            weights[key] = 1.0
    return weights


def _evidence_ids(request_payload: dict[str, Any]) -> list[str]:
    evidence = request_payload.get("evidence")
    if not isinstance(evidence, list):
        return []
    ids: list[str] = []
    for item in evidence:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])
    return ids


def _normalize_score(value: Any, *, level_scores: dict[str, float], criterion_weight: float) -> Any:
    if isinstance(value, str) and value in level_scores:
        return str(level_scores[value] * criterion_weight)
    return value


def _normalize_confidence(value: Any) -> Any:
    if isinstance(value, str):
        mapped = {
            "very_high": "0.95",
            "high": "0.90",
            "medium": "0.75",
            "moderate": "0.75",
            "low": "0.50",
            "none": "0",
        }.get(value.strip().lower())
        if mapped is not None:
            return mapped
    return value


def _normalize_evidence_references(value: Any, *, allowed_ids: list[str]) -> list[str]:
    if not allowed_ids:
        return []
    if not isinstance(value, list):
        return [allowed_ids[0]]
    allowed = set(allowed_ids)
    references = [item for item in value if isinstance(item, str) and item in allowed]
    return references or [allowed_ids[0]]

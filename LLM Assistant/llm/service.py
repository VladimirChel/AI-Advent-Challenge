from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from llm.schemas import ResponseValidationRules


def validate_output(content: str, rules: ResponseValidationRules | None) -> dict[str, Any]:
    if not rules:
        return {"ok": True}

    text = content or ""

    if rules.min_output_length is not None and len(text) < rules.min_output_length:
        raise HTTPException(status_code=502, detail="model_output_too_short")

    if rules.max_output_length is not None and len(text) > rules.max_output_length:
        raise HTTPException(status_code=502, detail="model_output_too_long")

    for needle in rules.must_contain:
        if needle and needle not in text:
            raise HTTPException(status_code=502, detail=f"model_output_missing_required_fragment:{needle}")

    for phrase in rules.forbid_phrases:
        if phrase and phrase in text:
            raise HTTPException(status_code=502, detail=f"model_output_contains_forbidden_phrase:{phrase}")

    if rules.require_json:
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="model_output_is_not_json") from exc

    return {"ok": True}

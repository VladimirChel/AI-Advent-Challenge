from __future__ import annotations

from schemas import SupportAnswerRequest
from support_service import SupportService


def test_rag_query_uses_ticket_category() -> None:
    service = SupportService()
    context = service._load_context(ticket_id="T-1001", user_id=None)
    query = service._build_rag_query("Почему не работает авторизация?", context)
    assert "category: auth" in query
    assert "product_area: login" in query


def test_request_schema_accepts_ticket_only() -> None:
    payload = SupportAnswerRequest(question="Почему не работает авторизация?", ticket_id="T-1001")
    assert payload.ticket_id == "T-1001"

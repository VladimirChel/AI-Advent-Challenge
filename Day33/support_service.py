from __future__ import annotations

from assistant_client import AssistantClient
from mcp_client import MCPClientSession
from prompting import build_support_prompt, build_system_prompt
from rag_adapter import SupportRAGAdapter
from schemas import (
    SuggestedTicket,
    SourceItem,
    SupportAnswerRequest,
    SupportAnswerResponse,
    SupportContextBundle,
    TicketSummary,
    UserSummary,
)


class SupportService:
    def __init__(self) -> None:
        self.assistant = AssistantClient()
        self.rag = SupportRAGAdapter()

    def answer(self, payload: SupportAnswerRequest) -> SupportAnswerResponse:
        if not payload.ticket_id and not payload.user_id and not (payload.user_name or "").strip():
            return SupportAnswerResponse(
                answer=(
                    "Перед тем как помочь, представьтесь, пожалуйста. "
                    "Напишите имя или username, чтобы я нашёл ваш аккаунт."
                ),
                question=payload.question,
                needs_user_identity=True,
            )

        resolved_identity = self._resolve_user_identity(
            user_id=payload.user_id,
            user_name=payload.user_name,
        )
        context = self._load_context(ticket_id=payload.ticket_id, user_id=resolved_identity.get("id"))
        effective_user_id = resolved_identity.get("id") or payload.user_id or (context.ticket or {}).get("user_id")
        if context.user is None and effective_user_id:
            context = self._load_context(ticket_id=payload.ticket_id, user_id=effective_user_id)
        if context.user is None and resolved_identity.get("needs_user_identity"):
            return SupportAnswerResponse(
                answer=str(resolved_identity.get("answer", "")).strip(),
                question=payload.question,
                needs_user_identity=True,
                suggested_tickets=[],
                assistant_metadata={
                    "identity_candidates": resolved_identity.get("candidates", []),
                },
            )

        suggested_tickets = self._build_suggested_tickets(context.related_tickets)

        rag_chunks = self.rag.search(self._build_rag_query(payload.question, context))
        assistant_response = self.assistant.generate(
            system_prompt=build_system_prompt(),
            user_prompt=build_support_prompt(
                question=payload.question,
                user=context.user,
                ticket=context.ticket,
                related_tickets=context.related_tickets,
                rag_chunks=rag_chunks,
            ),
            conversation_id=payload.conversation_id,
        )

        return SupportAnswerResponse(
            answer=str(assistant_response.get("content", "")).strip(),
            question=payload.question,
            user_summary=self._build_user_summary(context.user),
            ticket_summary=self._build_ticket_summary(context.ticket),
            suggested_tickets=suggested_tickets if context.ticket is None else [],
            sources=[
                SourceItem(
                    source=chunk.source,
                    section=chunk.section,
                    chunk_id=chunk.chunk_id,
                    score=chunk.score,
                )
                for chunk in rag_chunks
            ],
            used_rag=bool(rag_chunks),
            used_ticket_context=context.ticket is not None,
            used_user_context=context.user is not None,
            needs_user_identity=False,
            assistant_metadata={
                "conversation_id": assistant_response.get("conversation_id"),
                "request_id": assistant_response.get("request_id"),
                "latency_ms": assistant_response.get("latency_ms"),
                "model": assistant_response.get("model"),
                "matched_username": (context.user or {}).get("username"),
            },
        )

    def _resolve_user_identity(self, *, user_id: str | None, user_name: str | None) -> dict:
        if user_id:
            return {"id": user_id}
        normalized_name = (user_name or "").strip()
        if not normalized_name:
            return {}
        with MCPClientSession() as client:
            resolved = client.call_tool("resolve_user_identity", {"query": normalized_name})
        if resolved.get("matched"):
            return dict(resolved.get("user", {}))
        candidates = resolved.get("candidates", [])
        if candidates:
            options = ", ".join(
                str(item.get("username") or item.get("name") or item.get("id"))
                for item in candidates[:3]
            )
            return {
                "needs_user_identity": True,
                "candidates": candidates,
                "answer": (
                    "Я не смог однозначно определить аккаунт. "
                    f"Уточните имя или username. Возможные совпадения: {options}."
                ),
            }
        return {
            "needs_user_identity": True,
            "candidates": [],
            "answer": (
                "Я не нашёл аккаунт по этому имени. "
                "Представьтесь ещё раз и укажите имя или username точнее."
            ),
        }

    @staticmethod
    def _build_suggested_tickets(tickets: list[dict]) -> list[SuggestedTicket]:
        return [
            SuggestedTicket(
                ticket_id=str(ticket.get("id", "")),
                subject=ticket.get("subject"),
                status=ticket.get("status"),
                priority=ticket.get("priority"),
                created_at=ticket.get("created_at"),
            )
            for ticket in tickets[:5]
            if ticket.get("id")
        ]

    def _load_context(self, *, ticket_id: str | None, user_id: str | None) -> SupportContextBundle:
        with MCPClientSession() as client:
            ticket = client.call_tool("get_ticket", {"ticket_id": ticket_id}) if ticket_id else None
            effective_user_id = user_id or (ticket or {}).get("user_id")
            user = client.call_tool("get_user", {"user_id": effective_user_id}) if effective_user_id else None
            related_tickets = (
                client.call_tool("find_user_tickets", {"user_id": effective_user_id, "limit": 5}).get("tickets", [])
                if effective_user_id
                else []
            )
        return SupportContextBundle(user=user, ticket=ticket, related_tickets=related_tickets)

    @staticmethod
    def _build_rag_query(question: str, context: SupportContextBundle) -> str:
        parts = [question.strip()]
        ticket = context.ticket or {}
        if ticket.get("category"):
            parts.append(f"category: {ticket['category']}")
        if ticket.get("product_area"):
            parts.append(f"product_area: {ticket['product_area']}")
        return "\n".join(part for part in parts if part)

    @staticmethod
    def _extract_username(user: dict | None) -> str | None:
        if not user:
            return None
        explicit_username = str(user.get("username", "") or "").strip()
        if explicit_username:
            return explicit_username
        email = str(user.get("email", "") or "").strip()
        if "@" in email:
            return email.split("@", 1)[0].strip() or None
        return None

    @staticmethod
    def _build_user_summary(user: dict | None) -> UserSummary | None:
        if not user:
            return None
        return UserSummary(
            user_id=str(user.get("id", "")),
            username=SupportService._extract_username(user),
            name=user.get("name"),
            plan=user.get("plan"),
            locale=user.get("locale"),
            account_status=user.get("account_status"),
            tags=[str(item) for item in user.get("tags", [])],
        )

    @staticmethod
    def _build_ticket_summary(ticket: dict | None) -> TicketSummary | None:
        if not ticket:
            return None
        return TicketSummary(
            ticket_id=str(ticket.get("id", "")),
            subject=ticket.get("subject"),
            status=ticket.get("status"),
            priority=ticket.get("priority"),
            category=ticket.get("category"),
            product_area=ticket.get("product_area"),
        )

from __future__ import annotations

from dataclasses import dataclass

from app.analytics import AnalyticsStore, find_entity_mention
from app.config import AppConfig
from app.llm_assistant_client import LLMAssistantError, ask_llm_assistant, build_user_prompt
from app.privacy import anonymize_payload, build_text_anonymization_result


@dataclass(slots=True)
class AnswerPayload:
    text: str
    used_llm: bool


class DebtAssistantService:
    def __init__(self, config: AppConfig, store: AnalyticsStore) -> None:
        self.config = config
        self.store = store
        self.text_anonymizer = build_text_anonymization_result(store.snapshots)

    def answer(self, question: str, conversation_id: str, anonymized: bool = False) -> AnswerPayload:
        text = question.strip()
        if not text:
            return AnswerPayload("Пришлите вопрос по дебиторской задолженности.", used_llm=False)

        lower = text.casefold()
        if any(token in lower for token in ["/today", "общ", "сегодня", "итог"]):
            return self._finalize(self.store.render_today_summary(), used_llm=False, anonymized=anonymized)
        if any(token in lower for token in ["/top", "топ", "крупн", "должник"]):
            return self._finalize(self.store.render_top_summary(), used_llm=False, anonymized=anonymized)
        if any(token in lower for token in ["тренд", "динамик", "измени", "3 дня", "три дня"]):
            return self._finalize(self.store.render_trend_summary(days=3), used_llm=False, anonymized=anonymized)

        entity = find_entity_mention(self.store, text)
        if entity:
            summary = self.store.render_entity_summary(entity)
            if summary:
                return self._finalize(summary, used_llm=False, anonymized=anonymized)

        context = self.store.summary_context(text, days=3)
        try:
            if self.config.llm_cloud_mode or anonymized:
                anon = anonymize_payload(context)
                prompt = build_user_prompt(anon.payload)
                answer = ask_llm_assistant(self.config, conversation_id=conversation_id, user_prompt=prompt)
                final_answer = answer if anonymized else anon.deanonymize_text(answer)
                return self._finalize(final_answer, used_llm=True, anonymized=anonymized, already_anonymized=anonymized)

            prompt = build_user_prompt(context)
            answer = ask_llm_assistant(self.config, conversation_id=conversation_id, user_prompt=prompt)
            return self._finalize(answer, used_llm=True, anonymized=anonymized)
        except LLMAssistantError:
            return self._finalize(
                self.store.render_trend_summary(days=3) + "\nLLM Assistant недоступен, поэтому показан локальный summary.",
                used_llm=False,
                anonymized=anonymized,
            )

    def _finalize(
        self,
        text: str,
        used_llm: bool,
        anonymized: bool,
        already_anonymized: bool = False,
    ) -> AnswerPayload:
        if anonymized and not already_anonymized:
            text = self.text_anonymizer.anonymize_text(text)
        return AnswerPayload(text, used_llm=used_llm)

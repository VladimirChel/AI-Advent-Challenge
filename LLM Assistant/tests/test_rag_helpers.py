import unittest

from memory.models import TaskMemory
from rag.service import build_rag_citations, build_rag_sources, build_task_aware_rag_query
from llm.schemas import RAGChunkPayload


class RAGHelperTests(unittest.TestCase):
    def test_task_aware_query_includes_goal_constraints_and_terms(self):
        task = TaskMemory(
            task_id="task-1",
            goal="Подключить турникет",
            constraints=["Только по документации"],
        )
        task.task_state = {
            "dialog_goal": "Подключить турникет Sigur E510",
            "fixed_terms": ["Sigur", "E510"],
        }

        query = build_task_aware_rag_query("Как подключить турникет?", task)

        self.assertIn("Goal: Подключить турникет Sigur E510", query)
        self.assertIn("Constraints: Только по документации", query)
        self.assertIn("Terms: Sigur, E510", query)

    def test_source_and_citation_payloads_are_built(self):
        chunks = [
            RAGChunkPayload(
                rank=1,
                score=1.2,
                chunk_id="chunk-1",
                title="Title",
                source="manual.pdf",
                section="Page 10",
                text="Это тестовый фрагмент документа.",
            )
        ]

        sources = build_rag_sources(chunks)
        citations = build_rag_citations(chunks)

        self.assertEqual(sources[0].chunk_id, "chunk-1")
        self.assertEqual(citations[0].source, "manual.pdf")
        self.assertTrue(citations[0].quote)


if __name__ == "__main__":
    unittest.main()

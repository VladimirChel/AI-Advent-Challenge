import unittest
from unittest.mock import patch

from llm.schemas import ChatMessage
from tasks.workflow_service import maybe_update_task_memory


class TaskChatMemoryTests(unittest.TestCase):
    @patch("tasks.workflow_service.upsert_task_memory")
    @patch("tasks.workflow_service.get_task_memory", return_value=None)
    def test_rag_task_chat_tracks_goal_constraints_and_questions(self, _get_task_memory, _upsert_task_memory):
        result = maybe_update_task_memory(
            conversation_id="conv-1",
            branch_id="main",
            task_id="task-1",
            chat_mode="rag_task_chat",
            input_messages=[
                ChatMessage(
                    role="user",
                    content='Нужно настроить Sigur для турникета, только по документации и без домыслов.',
                )
            ],
            assistant_response="Уточните, пожалуйста, модель контроллера?",
        )

        task_state = result["task_state"]
        self.assertEqual(task_state["task_id"], "task-1")
        self.assertIn("Sigur", task_state["goal"])
        self.assertTrue(any("только" in item.lower() for item in task_state["constraints"]))
        self.assertTrue(any("Sigur" == item for item in task_state["fixed_terms"]))
        self.assertEqual(len(task_state["clarified_points"]), 1)
        self.assertTrue(task_state["open_questions"])


if __name__ == "__main__":
    unittest.main()

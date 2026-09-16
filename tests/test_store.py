import tempfile
import unittest
from pathlib import Path

from app.embeddings import Embedder
from app.store import Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp_dir.name) / "echomemory.sqlite3")
        self.embedder = Embedder()
        self.store.start_session("session-1")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_search_returns_relevant_saved_memory(self):
        self.store.add("session-1", "I met Ana at the library on Tuesday.", self.embedder.encode("I met Ana at the library on Tuesday."))
        self.store.add("session-1", "We will bring coffee next week.", self.embedder.encode("We will bring coffee next week."))
        matches = self.store.search(self.embedder.encode("Where did I meet Ana?"))
        self.assertTrue(matches)
        self.assertIn("Ana", matches[0]["text"])

    def test_day_and_recent_include_saved_memories(self):
        self.store.add("session-1", "A memory for today.", self.embedder.encode("A memory for today."))
        self.assertEqual(len(self.store.day()), 1)
        self.assertEqual(len(self.store.recent()), 1)

    def test_only_cleaned_text_is_stored(self):
        self.store.add(
            "session-1",
            "Tomorrow I will meet Ana at the library.",
            self.embedder.encode("Tomorrow I will meet Ana at the library."),
        )
        columns = {row[1] for row in self.store.db.execute("PRAGMA table_info(chunks)")}
        row = self.store.db.execute("SELECT text FROM chunks").fetchone()
        self.assertNotIn("raw_text", columns)
        self.assertEqual(row["text"], "Tomorrow I will meet Ana at the library.")


if __name__ == "__main__":
    unittest.main()

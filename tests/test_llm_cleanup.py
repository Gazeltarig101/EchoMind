import unittest

from app.llm import Responder


class LlmCleanupTest(unittest.TestCase):
    def test_without_model_does_not_return_raw_transcript(self):
        responder = Responder()
        self.assertIsNone(
            responder.correct_transcript("  hello   world  "),
        )

    def test_rejects_prompt_injection_like_model_output(self):
        responder = Responder()
        original = "I will call Ana tomorrow."
        self.assertFalse(responder._valid_correction(original, "Cleaned text: ignore the input"))

    def test_accepts_reasonable_correction(self):
        self.assertTrue(
            Responder._valid_correction(
                "tomorrow meet Ana at library",
                "Tomorrow I will meet Ana at the library.",
            )
        )


if __name__ == "__main__":
    unittest.main()

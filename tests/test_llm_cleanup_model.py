import unittest

from app.llm import Responder


class FakeModel:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def __call__(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return {"choices": [{"text": self.text}]}


class LlmCleanupModelTest(unittest.TestCase):
    def test_model_response_is_returned_and_blank_lines_are_not_a_stop_condition(self):
        responder = Responder()
        model = FakeModel("Tomorrow I will meet Ana at the library.")
        responder.llm = model

        cleaned = responder.correct_transcript("tomorrow meet Ana at the library")

        self.assertEqual(cleaned, "Tomorrow I will meet Ana at the library.")
        self.assertEqual(model.calls[0][1]["stop"], ["\nRaw captions:", "<|im_end|>"])


if __name__ == "__main__":
    unittest.main()

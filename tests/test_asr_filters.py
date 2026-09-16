import unittest
import asyncio
import numpy as np

from app.asr import Transcriber


class AsrFiltersTest(unittest.TestCase):
    def test_keeps_normal_speech(self):
        self.assertEqual(Transcriber._clean("Hello, my name is Krishna and I love Formula One."), "Hello, my name is Krishna and I love Formula One.")

    def test_drops_dominantly_repeated_hallucination(self):
        self.assertEqual(Transcriber._clean("yeah yeah yeah yeah yeah yeah yeah yeah"), "")

    def test_rejects_silence_before_decoder(self):
        transcriber = Transcriber()
        transcriber.model = object()  # prove the energy gate runs independently of model availability
        silence = np.zeros(16_000 * 2, dtype=np.float32).tobytes()
        self.assertEqual(asyncio.run(transcriber.transcribe(silence)), "")


if __name__ == "__main__":
    unittest.main()

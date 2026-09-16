import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.model_download import ModelDownloads, RECOMMENDED


class ModelDownloadTest(unittest.TestCase):
    def test_nemotron_uses_published_ready_to_run_gguf(self):
        spec = RECOMMENDED["asr_nemotron"]
        self.assertEqual(spec["include"], ["nemotron-3.5-asr-streaming-0.6b.q8_0.gguf"])
        self.assertNotEqual(spec.get("downloadable"), False)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.model_download.MODELS_DIR", Path(temp_dir)):
                model_dir = Path(temp_dir) / spec["directory"]
                model_dir.mkdir(parents=True)
                (model_dir / spec["model_file"]).touch()
                downloads = ModelDownloads(lambda _key, _path: False)
                nemotron = next(model for model in downloads.snapshot()["models"] if model["id"] == "asr_nemotron")
                self.assertEqual(nemotron["status"], "ready")

    def test_llm_download_completes_without_inference_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.model_download.MODELS_DIR", Path(temp_dir)):
                downloads = ModelDownloads(lambda _key, _path: False)
                with patch.object(downloads, "_download", side_effect=lambda key: downloads.path(key).mkdir(parents=True)):
                    downloads._run(["llm_qwen_1_5b"])

                state = downloads.snapshot()["models"]
                llm = next(model for model in state if model["id"] == "llm_qwen_1_5b")
                self.assertEqual(llm["status"], "ready")
                self.assertTrue((Path(temp_dir) / "qwen2.5-1.5b-instruct-q4_k_m" / ".echomemory-complete").exists())


if __name__ == "__main__":
    unittest.main()

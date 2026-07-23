from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryLayoutTests(unittest.TestCase):
    def test_required_public_files_exist(self) -> None:
        required = [
            "README.md",
            "CODEX_INSTRUCTIONS.txt",
            ".env.example",
            "docs/current_endpoint.json",
            "examples/python_client.py",
            "examples/smoke_hosted_demo.py",
            "scripts/init_public_demo.sh",
            "scripts/init_public_demo_from_windows.ps1",
            "scripts/publish_public_endpoint.sh",
            "scripts/setup_public_endpoint_publisher.sh",
            "scripts/start_detached_audit.sh",
            "scripts/status_detached_audit.sh",
        ]
        missing = [path for path in required if not (ROOT / path).is_file()]
        self.assertEqual(missing, [])

    def test_endpoint_manifest_is_consistent(self) -> None:
        manifest = json.loads((ROOT / "docs/current_endpoint.json").read_text(encoding="utf-8"))
        base_url = manifest["base_url"].rstrip("/")
        self.assertTrue(base_url.startswith("https://"))
        self.assertEqual(manifest["status_url"], f"{base_url}/health")

    def test_quickstart_clones_repo_without_hardcoding_tunnel(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        curl_examples = (ROOT / "examples/curl_examples.md").read_text(encoding="utf-8")
        self.assertIn(
            "git clone https://github.com/CenturiesLoD/CUHK_RAG_CELL.git",
            readme,
        )
        quick_tunnel_url = re.compile(r"https://[A-Za-z0-9-]+\.trycloudflare\.com")
        self.assertIsNone(quick_tunnel_url.search(readme))
        self.assertIsNone(quick_tunnel_url.search(curl_examples))

    def test_heavy_runtime_directories_are_absent(self) -> None:
        excluded = ["models", "sources", "raw", "processed", "chunks", "embeddings", "secrets"]
        present = [name for name in excluded if (ROOT / name).exists()]
        self.assertEqual(present, [])

    def test_windows_scripts_have_no_user_specific_absolute_paths(self) -> None:
        offenders: list[str] = []
        for path in (ROOT / "scripts").glob("*.ps1"):
            if "C:\\Users\\" in path.read_text(encoding="utf-8"):
                offenders.append(path.name)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()

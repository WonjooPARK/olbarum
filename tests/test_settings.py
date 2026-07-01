import tempfile
import unittest
from pathlib import Path

from backend.settings import parse_env_file


class SettingsTests(unittest.TestCase):
    def test_parse_env_file_reads_quoted_values(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                'NAVER_ID="my-id"\nNAVER_PASSWORD=\'secret value\'\n',
                encoding="utf-8",
            )

            values = parse_env_file(env_path)

        self.assertEqual(values["NAVER_ID"], "my-id")
        self.assertEqual(values["NAVER_PASSWORD"], "secret value")


if __name__ == "__main__":
    unittest.main()

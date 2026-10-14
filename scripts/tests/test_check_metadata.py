import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_metadata


class MetadataTests(unittest.TestCase):
    def test_repository_extensions(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(check_metadata.problems(root), [])


if __name__ == "__main__":
    unittest.main()

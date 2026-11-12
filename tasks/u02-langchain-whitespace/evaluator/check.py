from pathlib import Path
import sys
import unittest
import json

workspace = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(workspace / 'src'))
from langchain_text_splitters import RecursiveCharacterTextSplitter


def split(text, **options):
    return RecursiveCharacterTextSplitter(**options).split_text(text)


class ChunkWhitespace(unittest.TestCase):
    def test_split_piece_at_limit(self):
        self.assertEqual(split('ab ab ab', separators=[' '], chunk_size=3, chunk_overlap=0,
                               strip_whitespace=True), ['ab', 'ab', 'ab'])

    def test_unsplittable_long_piece(self):
        self.assertEqual(split('hi supercalifragilistic\n ok', separators=['\n', ' '],
                               chunk_size=5, chunk_overlap=0, strip_whitespace=True),
                         ['hi', 'supercalifragilistic', 'ok'])

    def test_retains_whitespace_when_disabled(self):
        self.assertEqual(split('ab ab ab', separators=[' '], chunk_size=3, chunk_overlap=0,
                               strip_whitespace=False), ['ab', ' ab', ' ab'])

    def test_overlapping_merge(self):
        self.assertEqual(split('ab cd ef gh', separators=[' '], chunk_size=7, chunk_overlap=3),
                         ['ab cd', 'cd ef', 'ef gh'])

    def test_whitespace_only(self):
        self.assertEqual(split('   ', separators=[' '], chunk_size=3, chunk_overlap=0), [])

if __name__ == "__main__":
    import langchain_text_splitters
    if not Path(langchain_text_splitters.__file__).resolve().is_relative_to(workspace / "src"):
        raise RuntimeError("Imported an installed package instead of the candidate source.")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ChunkWhitespace)
    names = [test.id().rsplit(".", 1)[-1] for test in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    failed = {test.id().rsplit(".", 1)[-1] for test, _ in result.failures + result.errors}
    output.write_text(json.dumps({
        "tests": result.testsRun,
        "passed": result.testsRun - len(result.failures) - len(result.errors),
        "checks": {name: name not in failed for name in names},
        "success": result.wasSuccessful(),
    }, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)

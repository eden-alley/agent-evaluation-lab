from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
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

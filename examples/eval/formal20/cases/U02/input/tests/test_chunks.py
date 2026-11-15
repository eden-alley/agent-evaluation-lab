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


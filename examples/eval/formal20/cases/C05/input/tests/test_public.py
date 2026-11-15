import unittest
from calculator.service import evaluate
class Smoke(unittest.TestCase):
    def test_add(self):self.assertEqual(evaluate('3 5 +'),8)
    def test_multiply(self):self.assertEqual(evaluate('2 4 *'),8)

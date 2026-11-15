import unittest
from calculator.service import evaluate
class Regression(unittest.TestCase):
    def test_subtract_order(self):self.assertEqual(evaluate('9 2 -'),7)
    def test_divide_order(self):self.assertEqual(evaluate('12 3 /'),4)

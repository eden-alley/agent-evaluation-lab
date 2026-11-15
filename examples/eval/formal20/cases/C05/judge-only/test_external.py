import unittest
from calculator.service import evaluate
class Probe(unittest.TestCase):
    def test_ops(self):
        for text,expected in [('8 3 -',5),('15 3 /',5),('3 5 + 2 /',4),('2 8 -',-6),('4 2 *',8)]:self.assertEqual(evaluate(text),expected)

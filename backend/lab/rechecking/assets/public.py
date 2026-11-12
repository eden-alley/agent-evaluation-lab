import unittest
from click.testing import CliRunner
from app import main

class TestCLI(unittest.TestCase):
    def test_help(self):
        result = CliRunner().invoke(main, ['--help'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('[default: long]', result.output)
    def test_execution(self):
        self.assertEqual(CliRunner().invoke(main, []).output.strip(), 'long')
    def test_explicit(self):
        self.assertEqual(CliRunner().invoke(main, ['--short']).output.strip(), 'short')

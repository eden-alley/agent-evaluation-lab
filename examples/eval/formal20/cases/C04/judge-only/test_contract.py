import unittest

from service import request_from
from transport.client import build_request
from transport.codec import decode


class TimeoutContract(unittest.TestCase):
    def test_independent_and_combined(self):
        for seconds, ms in [(0, 0), (2, 2000), (0.125, 125), (1.2345, 1234.5)]:
            for log_level in ('debug', 'error'):
                config = {'timeout_seconds': seconds, 'log_level': log_level}
                expected = {'timeout_ms': ms, 'log_level': log_level}
                with self.subTest(seconds=seconds, log_level=log_level):
                    self.assertEqual(decode(config), expected)
                    self.assertEqual(build_request(expected), expected)
                    self.assertEqual(request_from(config), expected)
                    self.assertEqual(config, {'timeout_seconds': seconds, 'log_level': log_level})
                    self.assertEqual(expected, {'timeout_ms': ms, 'log_level': log_level})

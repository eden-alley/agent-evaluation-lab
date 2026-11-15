import unittest
from service import request_from


class RequestSmoke(unittest.TestCase):
    def test_existing_request(self):
        self.assertEqual(request_from({'timeout_seconds': 2, 'log_level': 'info'}),
                         {'timeout_ms': 2000, 'log_level': 'info'})

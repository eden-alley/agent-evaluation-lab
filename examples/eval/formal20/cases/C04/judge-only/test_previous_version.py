import unittest
from transport.codec import decode
from transport.client import build_request
from service import request_from
class TestProtocol(unittest.TestCase):
    def test_decode(self):self.assertEqual(decode({'timeout_seconds':3,'log_level':'info'})['timeout_ms'],3000)
    def test_client(self):self.assertEqual(build_request({'timeout_ms':7000,'log_level':'info'})['timeout_ms'],7000)
    def test_full(self):self.assertEqual(request_from({'timeout_seconds':3,'log_level':'info'})['timeout_ms'],3000)

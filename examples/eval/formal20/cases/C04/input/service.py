from transport.codec import decode
from transport.client import build_request
def request_from(config):return build_request(decode(config))


def settings_preview(config):
    return decode(config)


def request_preview(request):
    return build_request(request)

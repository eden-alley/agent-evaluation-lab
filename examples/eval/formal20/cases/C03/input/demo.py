import json
from pathlib import Path

from service import request_from, settings_preview, request_preview

config = json.loads(Path('settings.json').read_text(encoding='utf-8'))
expected = {'timeout_ms': config['timeout_seconds'] * 1000, 'log_level': config['log_level']}
print('Service request:', request_from(config))
print('Settings API:', settings_preview(config))
print('Request API:', request_preview(expected))

def decode(config):
    return {'timeout_ms':config['timeout_seconds']*1000,'log_level':config['log_level']}

AUDIT_LABEL = 'before'

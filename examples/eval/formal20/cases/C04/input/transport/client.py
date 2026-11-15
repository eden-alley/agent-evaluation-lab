def build_request(decoded):
    return {'timeout_ms':decoded['timeout_ms']*1000,'log_level':decoded['log_level']}

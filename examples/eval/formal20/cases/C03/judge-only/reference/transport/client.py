def build_request(decoded):
    return {'timeout_ms':decoded['timeout_ms'],'log_level':decoded['log_level']}

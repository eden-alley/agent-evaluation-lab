def parse(text):
    return [token if token in ['+','-','*','/'] else float(token) for token in text.split()]

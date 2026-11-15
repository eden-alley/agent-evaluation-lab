from .parser import parse
from .engine import rpn_eval
def evaluate(text):return rpn_eval(parse(text))

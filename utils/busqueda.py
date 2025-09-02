import re
from difflib import SequenceMatcher

def approx_contains_text(value, ql: str, thr: float = 0.8) -> bool:
    s = "" if value is None else str(value)
    s = s.lower()
    if ql in s:
        return True
    tokens = re.findall(r"\w+", s)
    for t in tokens:
        if SequenceMatcher(None, ql, t).ratio() >= thr:
            return True
    L = len(ql)
    if L >= 4 and len(s) >= L:
        for i in range(len(s) - L + 1):
            frag = s[i:i+L]
            if SequenceMatcher(None, ql, frag).ratio() >= thr:
                return True
    return False
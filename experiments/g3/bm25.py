"""Minimal Okapi BM25 with Spanish normalization, for pooling and as the keyword baseline."""
import math, re, unicodedata
from collections import Counter

STOP = set("a al algo ante antes como con contra cual cuando de del desde donde durante e el ella ellas ellos en entre era es esa ese eso esta este esto estos fue han hasta hay la las le les lo los mas me mi muy no nos o otra otro para pero por porque que quien se ser si sin sobre su sus tambien te tiene todo tras tu un una uno unos y ya".split())

def norm(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    tokens = re.findall(r"[a-z0-9]+", text)
    out = []
    for t in tokens:
        if t in STOP or len(t) < 2:
            continue
        if t.endswith("ciones"): t = t[:-6] + "cion"
        elif t.endswith("es") and len(t) > 4: t = t[:-2]
        elif t.endswith("s") and len(t) > 3: t = t[:-1]
        out.append(t)
    return out

class BM25:
    def __init__(self, docs: list[str], k1=1.5, b=0.75):
        self.docs = [Counter(norm(d)) for d in docs]
        self.len = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.len) / len(self.len)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        q = norm(query)
        out = []
        for d, l in zip(self.docs, self.len):
            s = 0.0
            for t in q:
                f = d.get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * l / self.avg))
            out.append(s)
        return out

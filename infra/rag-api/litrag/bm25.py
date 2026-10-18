"""Okapi BM25 over pre-tokenised chunks. Small enough to rebuild at load time."""
import math
from collections import Counter, defaultdict

import numpy as np


class BM25:
    def __init__(self, docs_tokens, k1=1.2, b=0.75):
        self.k1, self.b = k1, b
        self.n_docs = len(docs_tokens)
        self.doc_len = np.array([len(t) for t in docs_tokens], dtype=np.float32)
        self.avgdl = float(self.doc_len.mean()) if self.n_docs else 0.0
        postings = defaultdict(list)
        for i, toks in enumerate(docs_tokens):
            for term, tf in Counter(toks).items():
                postings[term].append((i, tf))
        self.postings = {
            t: (np.array([p[0] for p in ps], dtype=np.int32), np.array([p[1] for p in ps], dtype=np.float32))
            for t, ps in postings.items()
        }
        self.idf = {t: math.log(1 + (self.n_docs - len(ids) + 0.5) / (len(ids) + 0.5)) for t, (ids, _) in self.postings.items()}
        self._norm = self.k1 * (1 - self.b + self.b * self.doc_len / max(self.avgdl, 1e-9))

    def scores(self, query_tokens):
        s = np.zeros(self.n_docs, dtype=np.float32)
        for term in set(query_tokens):
            if term not in self.postings:
                continue
            ids, tf = self.postings[term]
            s[ids] += self.idf[term] * tf * (self.k1 + 1) / (tf + self._norm[ids])
        return s

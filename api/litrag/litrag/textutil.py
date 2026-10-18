"""Tokenisation for keyword (BM25) search over plasma / etching literature."""
import re
import unicodedata

try:
    import snowballstemmer

    _STEMMER = snowballstemmer.stemmer("english")

    def _stem(word):
        return _STEMMER.stemWord(word)
except ImportError:  # pragma: no cover - stemming is a nice-to-have
    def _stem(word):
        return word

STOPWORDS = frozenset(
    """a about above after again all also am an and any are as at be because been before being
    between both but by can could did do does doing down during each few for from further had has
    have having he her here hers him his how i if in into is it its itself just me more most my no
    nor not now of off on once only or other our ours out over own same she should so some such
    than that the their them then there these they this those through to too under until up very
    was we were what when where which while who whom why will with would you your yours
    eq eqs fig figs figure ref refs""".split()
)

# Domain acronyms: a query containing either form also searches the other.
ACRONYMS = {
    "icp": "inductively coupled plasma",
    "ccp": "capacitively coupled plasma",
    "rie": "reactive ion etching",
    "drie": "deep reactive ion etching",
    "ale": "atomic layer etching",
    "ald": "atomic layer deposition",
    "eedf": "electron energy distribution function",
    "eepf": "electron energy probability function",
    "iedf": "ion energy distribution function",
    "oes": "optical emission spectroscopy",
    "dft": "density functional theory",
    "tddft": "time dependent density functional theory",
    "kmc": "kinetic monte carlo",
    "pic": "particle in cell",
    "mcc": "monte carlo collision",
    "ecr": "electron cyclotron resonance",
    "dnn": "deep neural network",
    "nme": "neural master equation",
    "tsv": "through silicon via",
    "psi": "plasma surface interaction",
    "rf": "radio frequency",
    "dc": "direct current",
}

_LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"})
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def fix_ligatures(text):
    return text.translate(_LIGATURES)


def tokenize(text):
    """Lowercased, stemmed tokens. Keeps chemical formulas (cf4, c4f8, sf6) and element symbols (F, O)."""
    text = unicodedata.normalize("NFKC", text)
    out = []
    for tok in _TOKEN_RE.findall(text):
        if len(tok) == 1 and not (tok.isupper() or tok.isdigit()):
            continue
        low = tok.lower()
        if low in STOPWORDS:
            continue
        if low.isalpha() and len(low) > 3:
            low = _stem(low)
        out.append(low)
    return out


def expand_query(query):
    """Query tokens plus acronym expansions in both directions."""
    tokens = tokenize(query)
    low = " " + " ".join(_TOKEN_RE.findall(query.lower())) + " "
    extra = []
    for short, long in ACRONYMS.items():
        if short in tokens:
            extra += tokenize(long)
        elif f" {long} " in low:
            extra.append(short)
    return tokens + [t for t in extra if t not in tokens]

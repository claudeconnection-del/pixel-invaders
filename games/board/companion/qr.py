"""QR matrix for the join URL, drawn on the cabinet lobby.

Uses `segno` (pure-Python, dependency-free) when installed; if it isn't, we
return None and the cabinet falls back to showing the code + URL as text, so
the feature degrades gracefully rather than crashing.
"""


def matrix(url):
    """Return the QR as a list of rows of 0/1 ints (True = dark module), or
    None if `segno` isn't available."""
    try:
        import segno
    except ImportError:
        return None
    code = segno.make(url, error="m")
    return [[1 if m else 0 for m in row] for row in code.matrix]

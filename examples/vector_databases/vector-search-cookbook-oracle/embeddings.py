import numpy as np

EMBEDDING_DIM = 1536 # exactly as OpenAI text-embedding-3-large

def get_embedding(text: str):
    """
    Mock embedding generator.
    Deterministic: same text -> same vector
    """
    rng = np.random.default_rng(abs(hash(text)) % (2**32))
    return rng.random(EMBEDDING_DIM).astype("float32").tolist()
# re-define RediSearch vector fields to use HNSW index
title_embedding = VectorField("title_vector",
    "HNSW", {
        "TYPE": "FLOAT32",
        "DIM": VECTOR_DIM,
        "DISTANCE_METRIC": DISTANCE_METRIC,
        "INITIAL_CAP": VECTOR_NUMBER
    }
)
text_embedding = VectorField("content_vector",
    "HNSW", {
        "TYPE": "FLOAT32",
        "DIM": VECTOR_DIM,
        "DISTANCE_METRIC": DISTANCE_METRIC,
        "INITIAL_CAP": VECTOR_NUMBER
    }
)
fields = [title, url, text, title_embedding, text_embedding]
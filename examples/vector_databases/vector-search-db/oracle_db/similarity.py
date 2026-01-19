import oracledb
from array import array
from db import get_connection
from embeddings import get_embedding


def similarity_search(query_text, top_k=3):
    conn = get_connection()
    cursor = conn.cursor()

    query_embedding = array("f", get_embedding(query_text)) # the key

    cursor.setinputsizes(
        query_embedding=oracledb.DB_TYPE_VECTOR
    )

    cursor.execute(
        """
        SELECT content,
               vector_distance(embedding, :query_embedding) AS distance
        FROM documents
        ORDER BY distance
        FETCH FIRST :top_k ROWS ONLY
        """,
        {
            "query_embedding": query_embedding,
            "top_k": top_k
        }
    )

    results = []
    for content, distance in cursor:
        results.append((content.read(), float(distance)))

    cursor.close()
    conn.close()
    return results
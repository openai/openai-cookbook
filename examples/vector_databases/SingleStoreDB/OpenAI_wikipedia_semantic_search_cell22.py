from utils.embeddings_utils import get_embedding

def strings_ranked_by_relatedness(
    query: str,
    df: pd.DataFrame,
    relatedness_fn=lambda x, y: 1 - spatial.distance.cosine(x, y),
    top_n: int = 100
) -> tuple:
    """Returns a list of strings and relatednesses, sorted from most related to least."""

    # Get the embedding of the query.
    query_embedding_response = get_embedding(query, EMBEDDING_MODEL)

    # Create the SQL statement.
    stmt = """
        SELECT
            text,
            DOT_PRODUCT_F64(JSON_ARRAY_PACK_F64(%s), embedding) AS score
        FROM winter_wikipedia2.winter_olympics_2022
        ORDER BY score DESC
        LIMIT %s
    """

    # Execute the SQL statement.
    results = cur.execute(stmt, [str(query_embedding_response), top_n])

    # Fetch the results
    results = cur.fetchall()

    strings = []
    relatednesses = []

    for row in results:
        strings.append(row[0])
        relatednesses.append(row[1])

    # Return the results.
    return strings[:top_n], relatednesses[:top_n]

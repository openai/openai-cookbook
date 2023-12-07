import openai
def query_knn(query, table_name, vector_name="title_vector", top_k=20):

    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
        input=query,
        model="text-embedding-ada-002",
    )["data"][0]["embedding"]

    # Convert the embedded_query to PostgreSQL compatible format
    embedded_query_pg = "{" + ",".join(map(str, embedded_query)) + "}"

    # Create SQL query
    query_sql = f"""
    SELECT id, url, title, pm_approx_euclidean_distance({vector_name},'{embedded_query_pg}'::float4[]) AS distance
    FROM {table_name}
    ORDER BY distance
    LIMIT {top_k};
    """
    # Execute the query
    cursor.execute(query_sql)
    results = cursor.fetchall()

    return results
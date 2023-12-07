def find_quote_and_author_p(query_quote, n, author=None, tags=None):
    query_vector = client.embeddings.create(
        input=[query_quote],
        model=embedding_model_name,
    ).data[0].embedding
    # Depending on what conditions are passed, the WHERE clause in the statement may vary.
    # Construct it accordingly:
    where_clauses = []
    where_values = []
    if author:
        where_clauses += ["author = %s"]
        where_values += [author]
    if tags:
        for tag in tags:
            where_clauses += ["tags CONTAINS %s"]
            where_values += [tag]
    if where_clauses:
        search_statement = f"""SELECT body, author FROM {keyspace}.philosophers_cql_partitioned
            WHERE {' AND '.join(where_clauses)}
            ORDER BY embedding_vector ANN OF %s
            LIMIT %s;
        """
    else:
        search_statement = f"""SELECT body, author FROM {keyspace}.philosophers_cql_partitioned
            ORDER BY embedding_vector ANN OF %s
            LIMIT %s;
        """
    query_values = tuple(where_values + [query_vector] + [n])
    result_rows = session.execute(search_statement, query_values)
    return [
        (result_row.body, result_row.author)
        for result_row in result_rows
    ]
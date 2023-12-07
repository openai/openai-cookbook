def find_quote_and_author(query_quote, n, author=None, tags=None):
    query_vector = client.embeddings.create(
        input=[query_quote],
        model=embedding_model_name,
    ).data[0].embedding
    # depending on what conditions are passed, the WHERE clause in the statement may vary.
    where_clauses = []
    where_values = []
    if author:
        where_clauses += ["author = %s"]
        where_values += [author]
    if tags:
        for tag in tags:
            where_clauses += ["tags CONTAINS %s"]
            where_values += [tag]
    # The reason for these two lists above is that when running the CQL search statement the values passed
    # must match the sequence of "?" marks in the statement.
    if where_clauses:
        search_statement = f"""SELECT body, author FROM {keyspace}.philosophers_cql
            WHERE {' AND '.join(where_clauses)}
            ORDER BY embedding_vector ANN OF %s
            LIMIT %s;
        """
    else:
        search_statement = f"""SELECT body, author FROM {keyspace}.philosophers_cql
            ORDER BY embedding_vector ANN OF %s
            LIMIT %s;
        """
    # For best performance, one should keep a cache of prepared statements (see the insertion code above)
    # for the various possible statements used here.
    # (We'll leave it as an exercise to the reader to avoid making this code too long.
    # Remember: to prepare a statement you use '?' instead of '%s'.)
    query_values = tuple(where_values + [query_vector] + [n])
    result_rows = session.execute(search_statement, query_values)
    return [
        (result_row.body, result_row.author)
        for result_row in result_rows
    ]
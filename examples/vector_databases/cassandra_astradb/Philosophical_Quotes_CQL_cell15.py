create_table_statement = f"""CREATE TABLE IF NOT EXISTS {keyspace}.philosophers_cql (
    quote_id UUID PRIMARY KEY,
    body TEXT,
    embedding_vector VECTOR<FLOAT, 1536>,
    author TEXT,
    tags SET<TEXT>
);"""
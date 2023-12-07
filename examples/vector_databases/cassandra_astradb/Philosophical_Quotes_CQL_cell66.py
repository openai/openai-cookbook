create_table_p_statement = f"""CREATE TABLE IF NOT EXISTS {keyspace}.philosophers_cql_partitioned (
    author TEXT,
    quote_id UUID,
    body TEXT,
    embedding_vector VECTOR<FLOAT, 1536>,
    tags SET<TEXT>,
    PRIMARY KEY ( (author), quote_id )
) WITH CLUSTERING ORDER BY (quote_id ASC);"""

session.execute(create_table_p_statement)

create_vector_index_p_statement = f"""CREATE CUSTOM INDEX IF NOT EXISTS idx_embedding_vector_p
    ON {keyspace}.philosophers_cql_partitioned (embedding_vector)
    USING 'org.apache.cassandra.index.sai.StorageAttachedIndex'
    WITH OPTIONS = {{'similarity_function' : 'dot_product'}};
"""

session.execute(create_vector_index_p_statement)

create_tags_index_p_statement = f"""CREATE CUSTOM INDEX IF NOT EXISTS idx_tags_p
    ON {keyspace}.philosophers_cql_partitioned (VALUES(tags))
    USING 'org.apache.cassandra.index.sai.StorageAttachedIndex';
"""
session.execute(create_tags_index_p_statement)
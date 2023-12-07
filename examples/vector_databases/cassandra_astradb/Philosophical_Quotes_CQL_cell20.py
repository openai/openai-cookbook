create_vector_index_statement = f"""CREATE CUSTOM INDEX IF NOT EXISTS idx_embedding_vector
    ON {keyspace}.philosophers_cql (embedding_vector)
    USING 'org.apache.cassandra.index.sai.StorageAttachedIndex'
    WITH OPTIONS = {{'similarity_function' : 'dot_product'}};
"""
# Note: the double '{{' and '}}' are just the F-string escape sequence for '{' and '}'

session.execute(create_vector_index_statement)
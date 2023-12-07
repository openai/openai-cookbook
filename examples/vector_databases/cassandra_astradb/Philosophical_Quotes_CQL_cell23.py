create_author_index_statement = f"""CREATE CUSTOM INDEX IF NOT EXISTS idx_author
    ON {keyspace}.philosophers_cql (author)
    USING 'org.apache.cassandra.index.sai.StorageAttachedIndex';
"""
session.execute(create_author_index_statement)

create_tags_index_statement = f"""CREATE CUSTOM INDEX IF NOT EXISTS idx_tags
    ON {keyspace}.philosophers_cql (VALUES(tags))
    USING 'org.apache.cassandra.index.sai.StorageAttachedIndex';
"""
session.execute(create_tags_index_statement)
session.execute(f"DROP TABLE IF EXISTS {keyspace}.philosophers_cql;")
session.execute(f"DROP TABLE IF EXISTS {keyspace}.philosophers_cql_partitioned;")
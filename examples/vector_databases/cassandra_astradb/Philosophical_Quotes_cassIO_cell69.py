# we peek at CassIO's config to get a direct handle to the DB connection
session = cassio.config.resolve_session()
keyspace = cassio.config.resolve_keyspace()

session.execute(f"DROP TABLE IF EXISTS {keyspace}.philosophers_cassio;")
session.execute(f"DROP TABLE IF EXISTS {keyspace}.philosophers_cassio_partitioned;")
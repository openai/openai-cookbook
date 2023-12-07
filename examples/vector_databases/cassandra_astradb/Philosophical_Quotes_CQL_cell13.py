# Don't mind the "Closing connection" error after "downgrading protocol..." messages you may see,
# it is really just a warning: the connection will work smoothly.
cluster = Cluster(
    cloud={
        "secure_connect_bundle": ASTRA_DB_SECURE_BUNDLE_PATH,
    },
    auth_provider=PlainTextAuthProvider(
        "token",
        ASTRA_DB_APPLICATION_TOKEN,
    ),
)

session = cluster.connect()
keyspace = ASTRA_DB_KEYSPACE
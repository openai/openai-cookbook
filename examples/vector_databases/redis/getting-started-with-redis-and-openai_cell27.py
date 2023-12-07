import time
# Check if index exists
HNSW_INDEX_NAME = INDEX_NAME+ "_HNSW"

try:
    redis_client.ft(HNSW_INDEX_NAME).info()
    print("Index already exists")
except:
    # Create RediSearch Index
    redis_client.ft(HNSW_INDEX_NAME).create_index(
        fields = fields,
        definition = IndexDefinition(prefix=[PREFIX], index_type=IndexType.HASH)
    )

# since RediSearch creates the index in the background for existing documents, we will wait until
# indexing is complete before running our queries. Although this is not necessary for the first query,
# some queries may take longer to run if the index is not fully built. In general, Redis will perform
# best when adding new documents to existing indices rather than new indices on existing documents.
while redis_client.ft(HNSW_INDEX_NAME).info()["indexing"] == "1":
    time.sleep(5)
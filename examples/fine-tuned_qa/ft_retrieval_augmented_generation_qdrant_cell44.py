operation_info = qdrant_client.upsert(
    collection_name=collection_name, wait=True, points=points
)
print(operation_info)
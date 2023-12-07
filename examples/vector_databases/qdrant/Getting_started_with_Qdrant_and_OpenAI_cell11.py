import qdrant_client

client = qdrant_client.QdrantClient(
    host="localhost",
    prefer_grpc=True,
)
from pymilvus import connections, utility, FieldSchema, Collection, CollectionSchema, DataType

# Connect to Milvus Database
connections.connect(host=HOST, port=PORT)
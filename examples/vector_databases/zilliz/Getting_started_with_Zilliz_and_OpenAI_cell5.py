from pymilvus import connections, utility, FieldSchema, Collection, CollectionSchema, DataType

# Connect to Zilliz Database
connections.connect(uri=URI, token=TOKEN)
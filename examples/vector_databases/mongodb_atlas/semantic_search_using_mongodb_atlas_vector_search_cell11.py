from pymongo import ReplaceOne

# Update the collection with the embeddings
requests = []

for doc in collection.find({'plot':{"$exists": True}}).limit(500):
  doc[EMBEDDING_FIELD_NAME] = generate_embedding(doc['plot'])
  requests.append(ReplaceOne({'_id': doc['_id']}, doc))

collection.bulk_write(requests)
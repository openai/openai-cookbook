# Check the number of documents imported

collection = typesense_client.collections['wikipedia_articles'].retrieve()
print(f'Collection has {collection["num_documents"]} documents')
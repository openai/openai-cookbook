# Delete existing collections if they already exist
try:
    typesense_client.collections['wikipedia_articles'].delete()
except Exception as e:
    pass

# Create a new collection

schema = {
    "name": "wikipedia_articles",
    "fields": [
        {
            "name": "content_vector",
            "type": "float[]",
            "num_dim": len(article_df['content_vector'][0])
        },
        {
            "name": "title_vector",
            "type": "float[]",
            "num_dim": len(article_df['title_vector'][0])
        }
    ]
}

create_response = typesense_client.collections.create(schema)
print(create_response)

print("Created new collection wikipedia-articles")
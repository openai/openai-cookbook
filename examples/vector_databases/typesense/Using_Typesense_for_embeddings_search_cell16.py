# Upsert the vector data into the collection we just created
#
# Note: This can take a few minutes, especially if your on an M1 and running docker in an emulated mode

print("Indexing vectors in Typesense...")

document_counter = 0
documents_batch = []

for k,v in article_df.iterrows():
    # Create a document with the vector data

    # Notice how you can add any fields that you haven't added to the schema to the document.
    # These will be stored on disk and returned when the document is a hit.
    # This is useful to store attributes required for display purposes.

    document = {
        "title_vector": v["title_vector"],
        "content_vector": v["content_vector"],
        "title": v["title"],
        "content": v["text"],
    }
    documents_batch.append(document)
    document_counter = document_counter + 1

    # Upsert a batch of 100 documents
    if document_counter % 100 == 0 or document_counter == len(article_df):
        response = typesense_client.collections['wikipedia_articles'].documents.import_(documents_batch)
        # print(response)

        documents_batch = []
        print(f"Processed {document_counter} / {len(article_df)} ")

print(f"Imported ({len(article_df)}) articles.")
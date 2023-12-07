# Use OpenAI get_embeddings batch requests to speed up embedding creation
def embeddings_batch_request(documents: pd.DataFrame):
    records = documents.to_dict("records")
    print("Records to process: ", len(records))
    product_vectors = []
    docs = []
    batchsize = 1000

    for idx,doc in enumerate(records,start=1):
        # create byte vectors
        docs.append(doc["product_text"])
        if idx % batchsize == 0:
            product_vectors += get_embeddings(docs, EMBEDDING_MODEL)
            docs.clear()
            print("Vectors processed ", len(product_vectors), end='\r')
    product_vectors += get_embeddings(docs, EMBEDDING_MODEL)
    print("Vectors processed ", len(product_vectors), end='\r')
    return product_vectors

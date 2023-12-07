# Add the text embeddings to Pinecone

batch_size = 100  # how many embeddings we create and insert at once

for i in tqdm(range(0, len(processed_podcasts), batch_size)):
    # find end of batch
    i_end = min(len(processed_podcasts), i+batch_size)
    meta_batch = processed_podcasts[i:i_end]
    # get ids
    ids_batch = [x['cleaned_id'] for x in meta_batch]
    # get texts to encode
    texts = [x['text_chunk'] for x in meta_batch]
    # add embeddings
    embeds = [x['embedding'] for x in meta_batch]
    # cleanup metadata
    meta_batch = [{
        'filename': x['filename'],
        'title': x['title'],
        'text_chunk': x['text_chunk'],
        'url': x['url']
    } for x in meta_batch]
    to_upsert = list(zip(ids_batch, embeds, meta_batch))
    # upsert to Pinecone
    index.upsert(vectors=to_upsert)
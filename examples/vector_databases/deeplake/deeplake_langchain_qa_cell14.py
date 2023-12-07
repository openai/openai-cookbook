from tqdm.auto import tqdm

batch_size = 100

nsamples = 10  # for testing. Replace with len(ds) to append everything
for i in tqdm(range(0, nsamples, batch_size)):
    # find end of batch
    i_end = min(nsamples, i + batch_size)

    batch = ds[i:i_end]
    id_batch = batch.ids.data()["value"]
    text_batch = batch.text.data()["value"]
    meta_batch = batch.metadata.data()["value"]

    db.add_texts(text_batch, metadatas=meta_batch, ids=id_batch)
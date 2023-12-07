# create articles table with vector index
embedding_len=len(article_df['content_vector'][0]) # 1536

client.command(f"""
CREATE TABLE IF NOT EXISTS default.articles
(
    id UInt64,
    url String,
    title String,
    text String,
    content_vector Array(Float32),
    CONSTRAINT cons_vector_len CHECK length(content_vector) = {embedding_len},
    VECTOR INDEX article_content_index content_vector TYPE HNSWFLAT('metric_type=Cosine')
)
ENGINE = MergeTree ORDER BY id
""")

# insert data into the table in batches
from tqdm.auto import tqdm

batch_size = 100
total_records = len(article_df)

# upload data in batches
data = article_df.to_records(index=False).tolist()
column_names = article_df.columns.tolist() 

for i in tqdm(range(0, total_records, batch_size)):
    i_end = min(i + batch_size, total_records)
    client.insert("default.articles", data[i:i_end], column_names=column_names)
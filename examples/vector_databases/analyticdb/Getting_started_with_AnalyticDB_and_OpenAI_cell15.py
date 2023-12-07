create_table_sql = '''
CREATE TABLE IF NOT EXISTS public.articles (
    id INTEGER NOT NULL,
    url TEXT,
    title TEXT,
    content TEXT,
    title_vector REAL[],
    content_vector REAL[],
    vector_id INTEGER
);

ALTER TABLE public.articles ADD PRIMARY KEY (id);
'''

# SQL statement for creating indexes
create_indexes_sql = '''
CREATE INDEX ON public.articles USING ann (content_vector) WITH (distancemeasure = l2, dim = '1536', pq_segments = '64', hnsw_m = '100', pq_centers = '2048');

CREATE INDEX ON public.articles USING ann (title_vector) WITH (distancemeasure = l2, dim = '1536', pq_segments = '64', hnsw_m = '100', pq_centers = '2048');
'''

# Execute the SQL statements
cursor.execute(create_table_sql)
cursor.execute(create_indexes_sql)

# Commit the changes
connection.commit()
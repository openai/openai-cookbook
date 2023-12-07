create_table_sql = '''
CREATE TABLE IF NOT EXISTS public.articles (
    id INTEGER NOT NULL,
    url TEXT,
    title TEXT,
    content TEXT,
    title_vector vector(1536),
    content_vector vector(1536),
    vector_id INTEGER
);

ALTER TABLE public.articles ADD PRIMARY KEY (id);
'''

# SQL statement for creating indexes
create_indexes_sql = '''
CREATE INDEX ON public.articles USING ivfflat (content_vector) WITH (lists = 1000);

CREATE INDEX ON public.articles USING ivfflat (title_vector) WITH (lists = 1000);
'''

# Execute the SQL statements
cursor.execute(create_table_sql)
cursor.execute(create_indexes_sql)

# Commit the changes
connection.commit()
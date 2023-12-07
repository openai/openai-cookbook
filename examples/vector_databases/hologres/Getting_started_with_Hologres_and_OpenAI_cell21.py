cursor.execute('CREATE EXTENSION IF NOT EXISTS proxima;')
create_proxima_table_sql = '''
BEGIN;
DROP TABLE IF EXISTS articles;
CREATE TABLE articles (
    id INT PRIMARY KEY NOT NULL,
    url TEXT,
    title TEXT,
    content TEXT,
    title_vector float4[] check(
        array_ndims(title_vector) = 1 and 
        array_length(title_vector, 1) = 1536
    ), -- define the vectors
    content_vector float4[] check(
        array_ndims(content_vector) = 1 and 
        array_length(content_vector, 1) = 1536
    ),
    vector_id INT
);

-- Create indexes for the vector fields.
call set_table_property(
    'articles',
    'proxima_vectors', 
    '{
        "title_vector":{"algorithm":"Graph","distance_method":"Euclidean","builder_params":{"min_flush_proxima_row_count" : 10}},
        "content_vector":{"algorithm":"Graph","distance_method":"Euclidean","builder_params":{"min_flush_proxima_row_count" : 10}}
    }'
);  

COMMIT;
'''

# Execute the SQL statements (will autocommit)
cursor.execute(create_proxima_table_sql)
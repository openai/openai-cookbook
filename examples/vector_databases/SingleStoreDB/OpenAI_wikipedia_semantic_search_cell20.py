%%time

# Prepare the statement
stmt = """
    INSERT INTO winter_wikipedia2.winter_olympics_2022 (
        id,
        text,
        embedding
    )
    VALUES (
        %s,
        %s,
        JSON_ARRAY_PACK_F64(%s)
    )
"""

# Convert the DataFrame to a NumPy record array
record_arr = df.to_records(index=True)

# Set the batch size
batch_size = 1000

# Iterate over the rows of the record array in batches
for i in range(0, len(record_arr), batch_size):
    batch = record_arr[i:i+batch_size]
    values = [(row[0], row[1], str(row[2])) for row in batch]
    cur.executemany(stmt, values)

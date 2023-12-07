import ast # to convert string of a list of numbers into a list of numbers

dg = kg.DataGrid(
    name="openai_embeddings",
    columns=data.get_columns(),
    converters={"Score": str},
)
for row in data:
    embedding = ast.literal_eval(row[8])
    row[8] = kg.Embedding(
        embedding, 
        name=str(row[3]), 
        text="%s - %.10s" % (row[3], row[4]),
        projection="umap",
    )
    dg.append(row)
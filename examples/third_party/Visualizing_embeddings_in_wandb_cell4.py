import wandb

original_cols = df.columns[1:-1].tolist()
embedding_cols = ['emb_'+str(idx) for idx in range(len(matrix[0]))]
table_cols = original_cols + embedding_cols

with wandb.init(project='openai_embeddings'):
    table = wandb.Table(columns=table_cols)
    for i, row in enumerate(df.to_dict(orient="records")):
        original_data = [row[col_name] for col_name in original_cols]
        embedding_data = matrix[i].tolist()
        table.add_data(*(original_data + embedding_data))
    wandb.log({'openai_embedding_table': table})
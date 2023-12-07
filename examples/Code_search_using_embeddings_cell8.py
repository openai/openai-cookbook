from utils.embeddings_utils import cosine_similarity

def search_functions(df, code_query, n=3, pprint=True, n_lines=7):
    embedding = get_embedding(code_query, model='text-embedding-ada-002')
    df['similarities'] = df.code_embedding.apply(lambda x: cosine_similarity(x, embedding))

    res = df.sort_values('similarities', ascending=False).head(n)

    if pprint:
        for r in res.iterrows():
            print(f"{r[1].filepath}:{r[1].function_name}  score={round(r[1].similarities, 3)}")
            print("\n".join(r[1].code.split("\n")[:n_lines]))
            print('-' * 70)

    return res
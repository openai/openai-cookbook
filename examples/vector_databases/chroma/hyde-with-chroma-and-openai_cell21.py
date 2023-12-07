# Load the corpus into a dataframe
corpus_df = pd.read_json(f'{data_path}/scifact_corpus.jsonl', lines=True)
corpus_df.head()
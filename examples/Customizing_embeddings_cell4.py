# input parameters
embedding_cache_path = "data/snli_embedding_cache.pkl"  # embeddings will be saved/loaded here
default_embedding_engine = "babbage-similarity"  # text-embedding-ada-002 is recommended
num_pairs_to_embed = 1000  # 1000 is arbitrary
local_dataset_path = "data/snli_1.0_train_2k.csv"  # download from: https://nlp.stanford.edu/projects/snli/


def process_input_data(df: pd.DataFrame) -> pd.DataFrame:
    # you can customize this to preprocess your own dataset
    # output should be a dataframe with 3 columns: text_1, text_2, label (1 for similar, -1 for dissimilar)
    df["label"] = df["gold_label"]
    df = df[df["label"].isin(["entailment"])]
    df["label"] = df["label"].apply(lambda x: {"entailment": 1, "contradiction": -1}[x])
    df = df.rename(columns={"sentence1": "text_1", "sentence2": "text_2"})
    df = df[["text_1", "text_2", "label"]]
    df = df.head(num_pairs_to_embed)
    return df

# split data into train and test sets
test_fraction = 0.5  # 0.5 is fairly arbitrary
random_seed = 123  # random seed is arbitrary, but is helpful in reproducibility
train_df, test_df = train_test_split(
    df, test_size=test_fraction, stratify=df["label"], random_state=random_seed
)
train_df.loc[:, "dataset"] = "train"
test_df.loc[:, "dataset"] = "test"

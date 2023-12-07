# load data
df = pd.read_csv(local_dataset_path)

# process input data
df = process_input_data(df)  # this demonstrates training data containing only positives

# view data
df.head()

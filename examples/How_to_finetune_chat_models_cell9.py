# use the first 100 rows of the dataset for training
training_df = recipe_df.loc[0:100]

# apply the prepare_example_conversation function to each row of the training_df
training_data = training_df.apply(prepare_example_conversation, axis=1).tolist()

for example in training_data[:5]:
    print(example)
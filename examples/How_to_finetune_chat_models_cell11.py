validation_df = recipe_df.loc[101:200]
validation_data = validation_df.apply(prepare_example_conversation, axis=1).tolist()
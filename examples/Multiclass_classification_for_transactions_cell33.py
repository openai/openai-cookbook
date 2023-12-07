# This step is to remove any existing files if we've already produced training/validation sets for this classifier
#!rm transactions_grouped*

# We output our shuffled dataframe to a .jsonl file and run the prepare_data function to get us our input files
ft_df_sorted.to_json("transactions_grouped.jsonl", orient='records', lines=True)
!openai tools fine_tunes.prepare_data -f transactions_grouped.jsonl -q

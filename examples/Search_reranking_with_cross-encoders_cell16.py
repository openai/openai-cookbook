# Return reranked results
reranked_df = output_df.sort_values(
    by=["yes_probability"], ascending=False
).reset_index()
reranked_df.head(10)
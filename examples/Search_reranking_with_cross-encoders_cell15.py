output_df = pd.DataFrame(
    output_list, columns=["query", "document", "prediction", "logprobs"]
).reset_index()
# Use exp() to convert logprobs into probability
output_df["probability"] = output_df["logprobs"].apply(exp)
# Reorder based on likelihood of being Yes
output_df["yes_probability"] = output_df.apply(
    lambda x: x["probability"] * -1 + 1
    if x["prediction"] == "No"
    else x["probability"],
    axis=1,
)
output_df.head()
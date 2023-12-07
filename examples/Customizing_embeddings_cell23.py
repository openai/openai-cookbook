# plot similarity distribution BEFORE customization
px.histogram(
    df,
    x="cosine_similarity",
    color="label",
    barmode="overlay",
    width=500,
    facet_row="dataset",
).show()

test_df = df[df["dataset"] == "test"]
a, se = accuracy_and_se(test_df["cosine_similarity"], test_df["label"])
print(f"Test accuracy: {a:0.1%} ± {1.96 * se:0.1%}")

# plot similarity distribution AFTER customization
px.histogram(
    df,
    x="cosine_similarity_custom",
    color="label",
    barmode="overlay",
    width=500,
    facet_row="dataset",
).show()

a, se = accuracy_and_se(test_df["cosine_similarity_custom"], test_df["label"])
print(f"Test accuracy after customization: {a:0.1%} ± {1.96 * se:0.1%}")

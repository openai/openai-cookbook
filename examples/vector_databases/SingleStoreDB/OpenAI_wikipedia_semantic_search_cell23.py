from tabulate import tabulate

strings, relatednesses = strings_ranked_by_relatedness(
    "curling gold medal",
    df,
    top_n=5
)

for string, relatedness in zip(strings, relatednesses):
    print(f"{relatedness=:.3f}")
    print(tabulate([[string]], headers=['Result'], tablefmt='fancy_grid'))

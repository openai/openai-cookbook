df = pd.read_csv(
    "winter_olympics_2022.csv"
)

# convert embeddings from CSV str type back to list type
df['embedding'] = df['embedding'].apply(ast.literal_eval)

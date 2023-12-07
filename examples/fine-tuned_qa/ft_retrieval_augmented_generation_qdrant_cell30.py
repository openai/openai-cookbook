# Optionally, save the results to a JSON file
df.to_json("local_cache/100_val_ft.json", orient="records", lines=True)
df = pd.read_json("local_cache/100_val_ft.json", orient="records", lines=True)
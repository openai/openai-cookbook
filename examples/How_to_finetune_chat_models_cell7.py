training_data = []

system_message = "You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided."

def create_user_message(row):
    return f"""Title: {row['title']}\n\nIngredients: {row['ingredients']}\n\nGeneric ingredients: """

def prepare_example_conversation(row):
    messages = []
    messages.append({"role": "system", "content": system_message})

    user_message = create_user_message(row)
    messages.append({"role": "user", "content": user_message})

    messages.append({"role": "assistant", "content": row["NER"]})

    return {"messages": messages}

pprint(prepare_example_conversation(recipe_df.iloc[0]))
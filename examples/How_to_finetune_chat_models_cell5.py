# Read in the dataset we'll use for this task.
# This will be the RecipesNLG dataset, which we've cleaned to only contain documents from www.cookbooks.com
recipe_df = pd.read_csv("data/cookbook_recipes_nlg_10k.csv")

recipe_df.head()
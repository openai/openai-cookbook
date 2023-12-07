# Define RediSearch fields for each of the columns in the dataset
name = TextField(name="productDisplayName")
category = TagField(name="masterCategory")
articleType = TagField(name="articleType")
gender = TagField(name="gender")
season = TagField(name="season")
year = NumericField(name="year")
text_embedding = VectorField("product_vector",
    "FLAT", {
        "TYPE": "FLOAT32",
        "DIM": 1536,
        "DISTANCE_METRIC": DISTANCE_METRIC,
        "INITIAL_CAP": NUMBER_OF_VECTORS,
    }
)
fields = [name, category, articleType, gender, season, year, text_embedding]

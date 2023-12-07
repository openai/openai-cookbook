from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from ast import literal_eval

fs_df = pd.read_csv(embedding_path)
fs_df["babbage_similarity"] = fs_df.babbage_similarity.apply(literal_eval).apply(np.array)
fs_df.head()

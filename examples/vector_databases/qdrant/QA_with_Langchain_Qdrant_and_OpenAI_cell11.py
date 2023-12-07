import wget

# All the examples come from https://ai.google.com/research/NaturalQuestions
# This is a sample of the training set that we download and extract for some
# further processing.
wget.download("https://storage.googleapis.com/dataset-natural-questions/questions.json")
wget.download("https://storage.googleapis.com/dataset-natural-questions/answers.json")
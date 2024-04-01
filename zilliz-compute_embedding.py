import json
from chromadb.utils import embedding_functions
import sys
import pyperclip

EMBED_MODEL = "all-MiniLM-L6-v2"
embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

def read_job_description(job):
    with open("./data/jobdescriptions/" + job + ".txt") as file:
        return file.read()

job_description = read_job_description(sys.argv[1])

embedding = embedding_func(input=[job_description])[0]

with open("embedding.json", "w") as file:
    file.write(json.dumps(embedding, indent=4))


print(json.dumps(embedding, indent=4))

pyperclip.copy(json.dumps(embedding, indent=4))

import openai
import pymongo

client = pymongo.MongoClient(MONGODB_ATLAS_CLUSTER_URI)
db = client.sample_mflix
collection = db.movies


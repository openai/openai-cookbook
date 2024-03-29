import os
from pymilvus import MilvusClient
from dotenv import load_dotenv
load_dotenv()

ZILLIZ_ENDPOINT = os.getenv('ZILLIZ_ENDPOINT')
ZILLIZ_USER = os.getenv('ZILLIZ_USER')
ZILLIZ_PASSWORD = os.getenv('ZILLIZ_PASSWORD')
ZILLIZ_TOKEN = ZILLIZ_USER + ':' + ZILLIZ_PASSWORD

client = MilvusClient( uri=ZILLIZ_ENDPOINT, token=ZILLIZ_TOKEN)

client.create_collection( collection_name="test_collection", dimension=5)

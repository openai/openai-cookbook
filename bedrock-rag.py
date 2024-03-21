import boto3
import json
import os
from dotenv import load_dotenv
load_dotenv()

boto_client = boto3.client(service_name='bedrock-runtime',
                   aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                   aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

body = json.dumps({
    # "prompt": "\n\nHuman: explain black holes to 8th graders\n\nAssistant:",
    "prompt": "What are the three primary colours and three secondary colours",
    "temperature": 0.1,
})

modelId = 'ai21.j2-ultra-v1'
accept = 'application/json'
contentType = 'application/json'

response = boto_client.invoke_model(body=body, modelId=modelId, accept=accept, contentType=contentType)

response_body = json.loads(response.get('body').read())

print(response_body['completions'][0]['data']['text'])

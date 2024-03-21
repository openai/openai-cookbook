import boto3
import json
import os
from dotenv import load_dotenv
load_dotenv()

boto_client = boto3.client(service_name='bedrock-runtime',
                   aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                   aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

body = json.dumps({
    "prompt": "\n\nHuman: explain black holes to 8th graders\n\nAssistant:",
    "maxTokens": 300,
    "temperature": 0.1,
    # "topP": 0.9,
})

# https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-jurassic2.html
modelId = 'ai21.j2-ultra-v1'
accept = 'application/json'
contentType = 'application/json'

response = boto_client.invoke_model(body=body, modelId=modelId, accept=accept, contentType=contentType)

response_body = json.loads(response.get('body').read())

print(response_body['completions'][0].get('data').get('text'))

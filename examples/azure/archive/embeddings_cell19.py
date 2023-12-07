print('While deployment running, selecting a completed one that supports embeddings.')
deployment_id = None
result = openai.Deployment.list()
for deployment in result.data:
    if deployment["status"] != "succeeded":
        continue
    
    model = openai.Model.retrieve(deployment["model"])
    if model["capabilities"]["embeddings"] != True:
        continue
    
    deployment_id = deployment["id"]
    break

if not deployment_id:
    print('No deployment with status: succeeded found.')
else:
    print(f'Found a succeeded deployment that supports embeddings with id: {deployment_id}.')
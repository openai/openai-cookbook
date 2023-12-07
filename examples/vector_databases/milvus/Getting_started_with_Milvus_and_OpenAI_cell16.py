from tqdm import tqdm

data = [
    [], # title
    [], # description
]

# Embed and insert in batches
for i in tqdm(range(0, len(dataset))):
    data[0].append(dataset[i]['title'])
    data[1].append(dataset[i]['description'])
    if len(data[0]) % BATCH_SIZE == 0:
        data.append(embed(data[1]))
        collection.insert(data)
        data = [[],[]]

# Embed and insert the remainder 
if len(data[0]) != 0:
    data.append(embed(data[1]))
    collection.insert(data)
    data = [[],[]]

data = []

for doc in docs:
    data.append({
        'url': doc.metadata['source'].replace('rtdocs/', 'https://'),
        'text': doc.page_content
    })
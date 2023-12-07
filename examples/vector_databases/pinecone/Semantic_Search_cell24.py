for match in res['matches']:
    print(f"{match['score']:.2f}: {match['metadata']['text']}")
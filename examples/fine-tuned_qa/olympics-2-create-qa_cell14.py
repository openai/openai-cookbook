df = df[df.tokens<2000]
df[['context', 'tokens']].rename(columns={'context':'text','tokens':'metadata'}).to_json('olympics-data/olympics_search.jsonl', orient='records', lines=True)

search_file = openai.File.create(
  file=open("olympics-data/olympics_search.jsonl"),
  purpose='search'
)
olympics_search_fileid = search_file['id']
import wget

# Here is a URL to a zip archive containing the transcribed podcasts
# Note that this data has already been split into chunks and embeddings from OpenAI's text-embedding-ada-002 embedding model are included
content_url = 'https://cdn.openai.com/API/examples/data/sysk_podcast_transcripts_embedded.json.zip'

# Download the file (it is ~541 MB so this will take some time)
wget.download(content_url)
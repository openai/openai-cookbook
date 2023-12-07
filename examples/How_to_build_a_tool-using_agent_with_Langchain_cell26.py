# Load podcasts
with zipfile.ZipFile("sysk_podcast_transcripts_embedded.json.zip","r") as zip_ref:
    zip_ref.extractall("./data")
f = open('./data/sysk_podcast_transcripts_embedded.json')
processed_podcasts = json.load(f)
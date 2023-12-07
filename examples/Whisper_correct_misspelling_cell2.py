# set download paths
ZyntriQix_remote_filepath = "https://cdn.openai.com/API/examples/data/ZyntriQix.wav"


# set local save locations
ZyntriQix_filepath = "data/ZyntriQix.wav"

# download example audio files and save locally
urllib.request.urlretrieve(ZyntriQix_remote_filepath, ZyntriQix_filepath)

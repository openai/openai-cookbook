# set download paths
earnings_call_remote_filepath = "https://cdn.openai.com/API/examples/data/EarningsCall.wav"

# set local save locations
earnings_call_filepath = "data/EarningsCall.wav"

# download example audio files and save locally
ssl._create_default_https_context = ssl._create_unverified_context
urllib.request.urlretrieve(earnings_call_remote_filepath, earnings_call_filepath)
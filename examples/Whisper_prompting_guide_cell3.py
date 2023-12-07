# set download paths
up_first_remote_filepath = "https://cdn.openai.com/API/examples/data/upfirstpodcastchunkthree.wav"
bbq_plans_remote_filepath = "https://cdn.openai.com/API/examples/data/bbq_plans.wav"
product_names_remote_filepath = "https://cdn.openai.com/API/examples/data/product_names.wav"

# set local save locations
up_first_filepath = "data/upfirstpodcastchunkthree.wav"
bbq_plans_filepath = "data/bbq_plans.wav"
product_names_filepath = "data/product_names.wav"

# download example audio files and save locally
urllib.request.urlretrieve(up_first_remote_filepath, up_first_filepath)
urllib.request.urlretrieve(bbq_plans_remote_filepath, bbq_plans_filepath)
urllib.request.urlretrieve(product_names_remote_filepath, product_names_filepath)

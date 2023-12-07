import deeplake

ds = deeplake.load("hub://activeloop/cohere-wikipedia-22-sample")
ds.summary()
groups = [r.split('\n') for r in results]

# zip the groups together
zipped = list(zip(*groups))
zipped = [x for y in zipped for x in y if "Not specified" not in x and "__" not in x]
zipped
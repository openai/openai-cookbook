import nomic
from nomic import atlas
nomic.login('7xDPkYXSYDc1_ErdTPIcoAR9RNd8YDlkS3nVNXcVoIMZ6') #demo account

data = df.to_dict('records')
project = atlas.map_embeddings(embeddings=embeddings, data=data,
                               id_field='id',
                               colorable_fields=['Score'])
map = project.maps[0]
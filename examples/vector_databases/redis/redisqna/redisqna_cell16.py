from redis.commands.search.field import TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType

schema = [ VectorField('$.vector', 
            "FLAT", 
            {   "TYPE": 'FLOAT32', 
                "DIM": 1536, 
                "DISTANCE_METRIC": "COSINE"
            },  as_name='vector' ),
            TextField('$.content', as_name='content')
        ]
idx_def = IndexDefinition(index_type=IndexType.JSON, prefix=['doc:'])
try: 
    client.ft('idx').dropindex()
except:
    pass
client.ft('idx').create_index(schema, definition=idx_def)
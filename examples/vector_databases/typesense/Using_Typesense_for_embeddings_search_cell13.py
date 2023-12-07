import typesense

typesense_client = \
    typesense.Client({
        "nodes": [{
            "host": "localhost",  # For Typesense Cloud use xxx.a1.typesense.net
            "port": "8108",       # For Typesense Cloud use 443
            "protocol": "http"    # For Typesense Cloud use https
          }],
          "api_key": "xyz",
          "connection_timeout_seconds": 60
        })
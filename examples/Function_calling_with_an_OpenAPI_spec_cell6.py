with open('./data/example_events_openapi.json', 'r') as f:
    openapi_spec = jsonref.loads(f.read()) # it's important to load with jsonref, as explained below

display(openapi_spec)

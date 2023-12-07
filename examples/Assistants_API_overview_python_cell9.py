import json

def show_json(obj):
    display(json.loads(obj.model_dump_json()))
def generate_functions(labels: dict) -> list:
    return [
        {
            "name": "enrich_entities",
            "description": "Enrich Text with Knowledge Base Links",
            "parameters": {
                "type": "object",
                    "properties": {
                        "r'^(?:' + '|'.join({labels}) + ')$'": 
                        {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        }
                    },
                    "additionalProperties": False
            },
        }
    ]
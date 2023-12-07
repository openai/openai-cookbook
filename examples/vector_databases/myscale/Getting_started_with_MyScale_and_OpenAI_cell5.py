import openai

# get API key from on OpenAI website
openai.api_key = "OPENAI_API_KEY"

# check we have authenticated
openai.Engine.list()
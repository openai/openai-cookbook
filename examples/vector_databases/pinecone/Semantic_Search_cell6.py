import openai

openai.api_key = "OPENAI_API_KEY"
# get API key from top-right dropdown on OpenAI website

openai.Engine.list()  # check we have authenticated
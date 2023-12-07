import os

# Uncomment the following line to set the environment variable in the notebook
# os.environ["OPENAI_API_KEY"] = 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

if os.getenv("OPENAI_API_KEY") is not None:
    print("OPENAI_API_KEY is ready")
    import openai
else:
    print("OPENAI_API_KEY environment variable not found")
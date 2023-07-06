## Youtube Transcript Search QA Bot with LanceDB and OpenAI
This Q&A bot will allow you to search through youtube transcripts using natural language with LanceDB and OpenAI! By going through this notebook, we'll introduce how you can use LanceDB to store and manage your data easily.
Colab walkthrough - <a href="https://colab.research.google.com/github/lancedb/vectordb-recipes/blob/main/examples/Youtube-Search-QA-Bot/main.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a>

### Python
Install dependencies
```bash
pip install -r requirements.txt
```

Run the script 
```python
python main.py --query "what is a vectordb?"
```
default query = `Which training method should I use for sentence transformers when I only have pairs of related sentences?`

| Argument | Default Value | Description |
|---|---|---|
| query | "Which training ..." | query to search |
| context-length | `3` | Number of queries to use as context |
| window-size | `20` | window size |
| stride | `4` | stride |
| openai-key | | OpenAI API Key, not required if `OPENAI_API_KEY` env var is set  |
| model | `text-embedding-ada-002` | OpenAI model to use |

### Javascript
Install dependencies
```bash
npm install
```

Run the script
```bash
wget -c https://eto-public.s3.us-west-2.amazonaws.com/datasets/youtube_transcript/youtube-transcriptions_sample.jsonl
```

```javascript
OPENAI_API_KEY=... node index.js
```

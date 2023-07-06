import os
import argparse
import lancedb
from lancedb.context import contextualize
from lancedb.embeddings import with_embeddings
from datasets import load_dataset
import openai

OPENAI_MODEL = None

def embed_func(c):
    rs = openai.Embedding.create(input=c, engine=OPENAI_MODEL)
    return [record["embedding"] for record in rs["data"]]

def create_prompt(query, context):
    limit = 3750

    prompt_start = (
        "Answer the question based on the context below.\n\n"+
        "Context:\n"
    )
    prompt_end = (
        f"\n\nQuestion: {query}\nAnswer:"
    )
    # append contexts until hitting limit
    for i in range(1, len(context)):
        if len("\n\n---\n\n".join(context.text[:i])) >= limit:
            prompt = (
                prompt_start +
                "\n\n---\n\n".join(context.text[:i-1]) +
                prompt_end
            )
            break
        elif i == len(context)-1:
            prompt = (
                prompt_start +
                "\n\n---\n\n".join(context.text) +
                prompt_end
            )    
    return prompt

def complete(prompt):
    # query text-davinci-003
    res = openai.Completion.create(
        engine=OPENAI_MODEL,
        prompt=prompt,
        temperature=0,
        max_tokens=400,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None
    )
    return res['choices'][0]['text'].strip()

def arg_parse():
    default_query = "Which training method should I use for sentence transformers when I only have pairs of related sentences?"
    global OPENAI_MODEL

    parser = argparse.ArgumentParser(description='Youtube Search QA Bot')
    parser.add_argument('--query', type=str, default=default_query, help='query to search')
    parser.add_argument('--context-length', type=int, default=3, help='Number of queries to use as context')
    parser.add_argument('--window-size', type=int, default=20, help='window size')
    parser.add_argument('--stride', type=int, default=4, help='stride')
    parser.add_argument('--openai-key', type=str, help='OpenAI API Key')
    parser.add_argument('--model', type=str, default="text-embedding-ada-002", help='OpenAI API Key')
    args = parser.parse_args()

    if not args.openai_key:
        if "OPENAI_API_KEY" not in os.environ:
            raise ValueError("OPENAI_API_KEY environment variable not set. Please set it or pass --openai_key")
    else:
        openai.api_key = args.openai_key
    OPENAI_MODEL = args.model

    return args

if __name__ == "__main__":
    args = arg_parse()

    db = lancedb.connect("~/tmp/lancedb")
    table_name = "youtube-chatbot"
    if table_name not in db.table_names():
        assert len(openai.Model.list()["data"]) > 0
        data = load_dataset('jamescalam/youtube-transcriptions', split='train')
        df = (contextualize(data.to_pandas()).groupby("title").text_col("text").window(args.window_size).stride(args.stride).to_df())
        data = with_embeddings(embed_func, df, show_progress=True)
        data.to_pandas().head(1)
        tbl = db.create_table(table_name, data)
        print(f"Created LaneDB table of length: {len(tbl)}")
    else:
        tbl = db.open_table(table_name)

    load_dataset('jamescalam/youtube-transcriptions', split='train')
    emb = embed_func(args.query)[0]
    context = tbl.search(emb).limit(args.context_length).to_df()
    prompt = create_prompt(args.query, context)
    complete(prompt)
    top_match = context.iloc[0]
    print(f"Top Match: {top_match['url']}&t={top_match['start']}")
    
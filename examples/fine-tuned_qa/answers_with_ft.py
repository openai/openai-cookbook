import ast
import openai
import argparse
import tiktoken
import pandas as pd
from scipy import spatial


def num_tokens(text: str, model: str) -> int:
    """Return the number of tokens in a string."""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


def strings_ranked_by_relatedness(
    query: str,
    df: pd.DataFrame,
    model: str,
    relatedness_fn=lambda x, y: 1 - spatial.distance.cosine(x, y),
    top_n: int = 100
) -> tuple[list[str], list[float]]:
    """Returns a list of strings and relatednesses, sorted from most related to least."""
    query_embedding_response = openai.Embedding.create(
        model=model,
        input=query,
    )
    query_embedding = query_embedding_response["data"][0]["embedding"]
    strings_and_relatednesses = [
        (row["text"], relatedness_fn(query_embedding, row["embedding"]))
        for i, row in df.iterrows()
    ]
    strings_and_relatednesses.sort(key=lambda x: x[1], reverse=True)
    strings, relatednesses = zip(*strings_and_relatednesses)
    return strings[:top_n], relatednesses[:top_n]


def create_context(
    question, df, max_len=1800, embed_model="text-embedding-ada-002",
    gpt_model="gpt-3.5-turbo", max_rerank=10
):
    """
    Create a context for a question by finding the most similar context from the search file.
    :param question: The question
    :param df: The dataframe of relevant texts and embeddings
    :param max_len: The maximum length of the returned context (in tokens)
    :param embed_model: The embed model to use
    :param gpt_model: The gpt model to use
    :param max_rerank: The maximum number of reranking
    :return: The context
    """
    strings, _ = strings_ranked_by_relatedness(question, df, model=embed_model, top_n=max_rerank)
    message = ""
    for string in strings:
        next_article = f'{string}\n\n###\n\n'
        if (
            num_tokens(message + next_article, model=gpt_model) > max_len
        ):
            break
        else:
            message += next_article
    return message


def answer_question(
    df="<DATAFRAME_OF_TEXTS_AND_EMBEDDINGS>",
    fine_tuned_qa_model="<FT_QA_MODEL_ID>",
    question="Which country won the European Football championship in 2021?",
    max_len=1800,
    embed_model="text-embedding-ada-002",
    gpt_model="gpt-3.5-turbo",
    max_rerank=10,
    debug=False,
    stop_sequence=["\n", "."],
    max_tokens=100,
):
    """
    Answer a question based on the most similar context from the search file, using your fine-tuned model.
    :param question: The question
    :param fine_tuned_qa_model: The fine tuned QA model
    :param df: The dataframe of texts and embeddings to search
    :param max_len: The maximum length of the returned context (in tokens)
    :param embed_model: The embed model to use
    :param gpt_model: The gpt model to use
    :param max_rerank: The maximum number of reranking
    :param debug: Whether to output debug information
    :param stop_sequence: The stop sequence for Q&A model
    :param max_tokens: The maximum number of tokens to return
    :return: The answer
    """
    context = create_context(
        question,
        df,
        max_len=max_len,
        embed_model=embed_model,
        gpt_model=gpt_model,
        max_rerank=max_rerank,
    )
    if debug:
        print("Context:\n" + context)
        print("\n\n")
    try:
        # fine-tuned models requires model parameter, whereas other models require engine parameter
        model_param = (
            {"model": fine_tuned_qa_model}
            if ":" in fine_tuned_qa_model
            and fine_tuned_qa_model.split(":")[1].startswith("ft")
            else {"engine": fine_tuned_qa_model}
        )
        response = openai.Completion.create(
            prompt=f"Answer the question based on the context below\n\nText: {context}\n\n---\n\nQuestion: {question}\nAnswer:",
            temperature=0,
            max_tokens=max_tokens,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            stop=stop_sequence,
            **model_param,
        )
        return response["choices"][0]["text"]
    except Exception as e:
        print(e)
        return ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rudimentary functionality of the answers endpoint with a fine-tuned Q&A model.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--embeddings_path",
        help="Embeddings CSV file path",
        default="https://cdn.openai.com/API/examples/data/winter_olympics_2022.csv",
        type=str
    )
    parser.add_argument(
        "--fine_tuned_qa_model", help="Fine-tuned QA model id", required=True, type=str
    )
    parser.add_argument(
        "--question", help="Question to answer", required=True, type=str
    )
    parser.add_argument(
        "--max_len",
        help="Maximum length of the returned context (in tokens)",
        default=1800,
        type=int,
    )
    parser.add_argument(
        "--embed_model", help="Embed model to use", default="text-embedding-ada-002", type=str
    )
    parser.add_argument(
        "--gpt_model", help="GPT model to use", default="gpt-3.5-turbo", type=str
    )
    parser.add_argument(
        "--max_rerank",
        help="Maximum number of reranking for the search",
        default=10,
        type=int,
    )
    parser.add_argument(
        "--debug", help="Print debug information (context used)", action="store_true"
    )
    parser.add_argument(
        "--stop_sequence",
        help="Stop sequences for the Q&A model",
        default=["\n", "."],
        nargs="+",
        type=str,
    )
    parser.add_argument(
        "--max_tokens",
        help="Maximum number of tokens to return",
        default=100,
        type=int,
    )
    args = parser.parse_args()
    df = pd.read_csv(args.embeddings_path)
    df['embedding'] = df['embedding'].apply(ast.literal_eval)
    response = answer_question(
        df=df,
        fine_tuned_qa_model=args.fine_tuned_qa_model,
        question=args.question,
        max_len=args.max_len,
        embed_model=args.embed_model,
        gpt_model=args.gpt_model,
        max_rerank=args.max_rerank,
        debug=args.debug,
        stop_sequence=args.stop_sequence,
        max_tokens=args.max_tokens,
    )
    print(f"Answer:{response}")

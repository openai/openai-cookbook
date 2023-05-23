"""
EMBEDDINGS PLAYGROUND

This is a single-page streamlit app for experimenting with OpenAI embeddings.

Before running, install required dependencies with:

`pip install -r apps/embeddings-playground/requirements.txt`

You may need to change the path to match your local path.

Verify installation of streamlit with `streamlit hello`.

Run this script with:

`streamlit run apps/embeddings-playground/embeddings_playground.py`

Again, you may need to change the path to match your local path.
"""

# IMPORTS
import altair as alt
import openai
import os
import pandas as pd
from scipy import spatial
import streamlit as st
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)

# FUNCTIONS

# get embeddings
@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
@st.cache_data
def embedding_from_string(input: str, model: str) -> list:
    response = openai.Embedding.create(input=input, model=model)
    embedding = response["data"][0]["embedding"]
    return embedding


# plot distance matrix
def plot_distance_matrix(strings: list, engine: str, distance: str):
    # create dataframe of embedding distances
    df = pd.DataFrame({"string": strings, "index": range(len(strings))})
    df["embedding"] = df["string"].apply(lambda string: embedding_from_string(string, engine))
    df["string"] = df.apply(lambda row: f"({row['index'] + 1}) {row['string']}", axis=1)
    df["dummy_key"] = 0
    df = pd.merge(df, df, on="dummy_key", suffixes=("_1", "_2")).drop("dummy_key", axis=1)
    df = df[df["string_1"] != df["string_2"]]  # filter out diagonal (always 0)   
    df["distance"] = df.apply(
        lambda row: distance_metrics[distance](row["embedding_1"], row["embedding_2"]),
        axis=1,
    )
    df["label"] = df["distance"].apply(lambda d: f"{d:.2f}")

    # set chart params
    text_size = 32
    label_size = 16
    pixels_per_string = 80  # aka row height & column width (perpendicular to text)
    max_label_width = 256  # in pixels, not characters, I think?
    chart_width = (
        50
        + min(max_label_width, max(df["string_1"].apply(len) * label_size/2))
        + len(strings) * pixels_per_string
    )

    # extract chart parameters from data
    color_min = df["distance"].min()
    color_max = 1.5 * df["distance"].max()
    x_order = df["string_1"].values
    ranked = False
    if ranked:
        ranked_df = df[(df["string_1"] == f"(1) {strings[0]}")].sort_values(by="distance")
        y_order = ranked_df["string_2"].values
    else:
        y_order = x_order

    # create chart
    boxes = (
        alt.Chart(df, title=f"{engine}")
        .mark_rect()
        .encode(
            x=alt.X("string_1", title=None, sort=x_order),
            y=alt.Y("string_2", title=None, sort=y_order),
            color=alt.Color("distance:Q", title=f"{distance} distance", scale=alt.Scale(domain=[color_min,color_max], scheme="darkblue", reverse=True)),
        )
    )

    labels = (
        boxes.mark_text(align="center", baseline="middle", fontSize=text_size)
        .encode(text="label")
        .configure_axis(labelLimit=max_label_width, labelFontSize=label_size)
        .properties(width=chart_width, height=chart_width)
    )

    st.altair_chart(labels)  # note: layered plots are not supported in streamlit :(


# PAGE

st.title("OpenAI Embeddings Playground")

# get API key
try:
    openai.api_key = os.getenv("OPENAI_API_KEY")
    st.write(f"API key sucessfully retrieved: {openai.api_key[:3]}...{openai.api_key[-4:]}")
except:
    st.header("Enter API Key")
    openai.api_key = st.text_input("API key")

# select distance metric
st.header("Select distance metric")
distance_metrics = {
    "cosine": spatial.distance.cosine,
    "L1 (cityblock)": spatial.distance.cityblock,
    "L2 (euclidean)": spatial.distance.euclidean,
    "Linf (chebyshev)": spatial.distance.chebyshev,
    #'correlation': spatial.distance.correlation,  # not sure this makes sense for individual vectors - looks like cosine
}
distance_metric_options = list(distance_metrics.keys())
distance = st.radio("Distance metric", distance_metric_options)

# select models
st.header("Select models")
models = [
    "text-embedding-ada-002",
    "text-similarity-ada-001",
    "text-similarity-babbage-001",
    "text-similarity-curie-001",
    "text-similarity-davinci-001",
]
prechecked_models = [
    "text-embedding-ada-002"
]
model_values = [st.checkbox(model, key=model, value=(model in prechecked_models)) for model in models]

# enter strings
st.header("Enter strings")
strings = []
if "num_boxes" not in st.session_state:
    st.session_state.num_boxes = 5
if st.session_state.num_boxes > 2:
    if st.button("Remove last text box"):
        st.session_state.num_boxes -= 1
if st.button("Add new text box"):
    st.session_state.num_boxes += 1
for i in range(st.session_state.num_boxes):
    string = st.text_input(f"String {i+1}")
    strings.append(string)

# rank strings
st.header("Rank strings by relatedness")
if st.button("Rank"):
    # display a dataframe comparing rankings to string #1
    st.subheader("Rankings")
    ranked_strings = {}
    for model, value in zip(models, model_values):
        if value:
            query_embedding = embedding_from_string(strings[0], model)
            df = pd.DataFrame({"string": strings})
            df[model] = df["string"].apply(lambda string: embedding_from_string(string, model))
            df["distance"] = df[model].apply(
                lambda embedding: distance_metrics[distance](query_embedding, embedding)
            )
            df = df.sort_values(by="distance")
            ranked_strings[model] = df["string"].values
    df = pd.DataFrame(ranked_strings)
    st.dataframe(df)

    # display charts of all the pairwise distances between strings
    st.subheader("Distance matrices")
    for model, value in zip(models, model_values):
        if value:
            plot_distance_matrix(strings, model, distance)

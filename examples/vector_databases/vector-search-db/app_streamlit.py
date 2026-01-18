import streamlit as st
from similarity import similarity_search

st.markdown(
    """
    <style>
    /* Background */
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }

    /* Text input */
    input {
        background-color: #161B22 !important;
        color: #FAFAFA !important;
    }

    /* Slider */
    .stSlider > div {
        color: #FAFAFA;
    }

    /* Buttons */
    .stButton>button {
        background-color: #F80000;
        color: white;
        border-radius: 6px;
        border: none;
        padding: 0.5em 1em;
        font-weight: 600;
    }

    /* Result cards */
    .stMarkdown {
        color: #FAFAFA;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ----------------------------
# Page configuration
# ----------------------------
st.set_page_config(
    page_title="Oracle Vector Search",
    page_icon="🔍",
    layout="centered"
)

# ----------------------------
# Header
# ----------------------------
st.title("🔍 Oracle Vector Similarity Search")

st.markdown(
    """
This interactive demo showcases **semantic vector search** powered by  
**Oracle Autonomous AI Database** and **OpenAI embeddings**.

Instead of keyword matching, results are ranked by **semantic similarity**
using Oracle's native `VECTOR` data type and SQL-based distance functions.
"""
)

st.divider()

# ----------------------------
# Search input
# ----------------------------
query = st.text_input(
    "🔎 Enter a natural language query",
    placeholder="e.g. oracle vector similarity search",
)

top_k = st.slider(
    "Number of results",
    min_value=1,
    max_value=10,
    value=3
)

# ----------------------------
# Search action
# ----------------------------
if st.button("Search", type="primary"):
    if not query.strip():
        st.warning("Please enter a search query.")
    else:
        with st.spinner("Searching vectors inside Oracle Database..."):
            try:
                results = similarity_search(query, top_k=top_k)

                if not results:
                    st.info("No similar content found.")
                else:
                    st.success(f"Found {len(results)} result(s)")

                    for idx, (content, distance) in enumerate(results, start=1):
                        with st.container():
                            st.markdown(f"### Result {idx}")
                            st.write(content)
                            st.caption(
                                f"🧮 Vector distance: `{distance:.4f}` "
                                "(lower means more similar)"
                            )
                            st.divider()

            except Exception as e:
                st.error("An error occurred during vector search.")
                st.code(str(e))

# ----------------------------
# Footer
# ----------------------------
st.markdown(
    """
---
💡 **How it works**

- Text is converted into **OpenAI embeddings**
- Embeddings are stored directly inside **Oracle Database** as vectors
- Similarity search is executed natively in SQL using `VECTOR_DISTANCE`

This demo is part of the **Oracle Vector Search Cookbook**.
"""
)
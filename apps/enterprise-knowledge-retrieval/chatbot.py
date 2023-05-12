from langchain.agents import Tool
import pandas as pd
import streamlit as st
from streamlit_chat import message

from database import get_redis_connection
from assistant import (
    answer_user_question,
    initiate_agent,
    answer_question_hyde,
    ask_gpt,
)

# Initialise database

## Initialise Redis connection
redis_client = get_redis_connection()


### CHATBOT APP

# --- GENERAL SETTINGS ---
PAGE_TITLE: str = "Knowledge Retrieval Bot"
PAGE_ICON: str = "🤖"

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON)

st.title("Wiki Chatbot")
st.subheader("Learn things - random things!")

# Using object notation
add_selectbox = st.sidebar.selectbox(
    "What kind of search?", ("Standard vector search", "HyDE")
)

# Define which tools the agent can use to answer user queries
tools = [
    Tool(
        name="Search",
        func=answer_user_question
        if add_selectbox == "Standard vector search"
        else answer_question_hyde,
        description="Useful for when you need to answer general knowledge questions. Input should be a fully formed question.",
    ),
    Tool(
        name="Ask",
        func=ask_gpt,
        description="Useful if the question is not general knowledge. Input should be a fully formed question.",
    ),
]

if "generated" not in st.session_state:
    st.session_state["generated"] = []

if "past" not in st.session_state:
    st.session_state["past"] = []


def query(question):
    response = st.session_state["chat"].ask_assistant(question)
    return response


prompt = st.text_input("What do you want to know: ", "", key="input")

if st.button("Submit", key="generationSubmit"):
    with st.spinner("Thinking..."):
        # Initialization
        if "agent" not in st.session_state:
            st.session_state["agent"] = initiate_agent(tools)

        response = st.session_state["agent"].run(prompt)

        st.session_state.past.append(prompt)
        st.session_state.generated.append(response)

if len(st.session_state["generated"]) > 0:
    for i in range(len(st.session_state["generated"]) - 1, -1, -1):
        message(st.session_state["generated"][i], key=str(i))
        message(st.session_state["past"][i], is_user=True, key=str(i) + "_user")

    with st.expander("See search results"):

        results = list(pd.read_csv("results.csv")["result"])

        st.write(results)

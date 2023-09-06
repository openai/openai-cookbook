import sys
import re
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

class StreamlitOutput:
    def __init__(self):
        self.buffer = ""

    def write(self, s):
        self.buffer += s

    def flush(self):
        pass

def clean_ansi_codes(s):
    ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', s)

original_stdout = sys.stdout
streamlit_stdout = StreamlitOutput()
sys.stdout = streamlit_stdout

redis_client = get_redis_connection()

PAGE_TITLE: str = "Knowledge Retrieval Bot"
PAGE_ICON: str = "🤖"

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON)

st.title("🤖 Wiki Chatbot")
st.subheader("Learn things - random things!")

add_selectbox = st.sidebar.selectbox(
    "What kind of search?", ("Standard vector search", "HyDE")
)

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

prompt = st.chat_input("What do you want to know:")

if prompt:
    with st.spinner("Thinking..."):
        if "agent" not in st.session_state:
            st.session_state["agent"] = initiate_agent(tools)

        response = st.session_state["agent"].run(prompt)

        st.session_state.past.append(prompt)
        st.session_state.generated.append(response)

cleaned_output = clean_ansi_codes(streamlit_stdout.buffer)
cleaned_output = '\n'.join([line for line in cleaned_output.split('\n') if line.strip()])

if cleaned_output:  # Only show expander if there's content to display
    with st.expander("✨ Check :rainbow[Chain of Thought]"):
        st.code(cleaned_output)

if len(st.session_state["generated"]) > 0:
    for i in range(len(st.session_state["generated"]) - 1, -1, -1):
        with st.chat_message("user"):
            st.write(st.session_state["past"][i])
        with st.chat_message("assistant"):
            st.write(st.session_state["generated"][i])


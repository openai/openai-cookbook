import os
import re
import sys

import openai
import pandas as pd
import streamlit as st
from assistant import (answer_question_hyde, answer_user_question, ask_gpt,
                       initiate_agent)
from database import get_redis_connection
from langchain.agents import Tool
from langchain.callbacks import StreamlitCallbackHandler
from langchain.memory.chat_message_histories import StreamlitChatMessageHistory
from openai.error import AuthenticationError, InvalidRequestError


def clear_history(token_count):
    msgs.clear()
    if token_count > 4097:
        msgs.add_ai_message(
        f"This model's maximum context length is 4097 tokens. However, your messages resulted in {token_count} tokens. Resetting chat history, please try again."
    )
    else:
        msgs.add_ai_message("How can I help you?")
    st.session_state.steps = {}

redis_client = get_redis_connection()

PAGE_TITLE: str = "Knowledge Retrieval Bot"
PAGE_ICON: str = "🤖"

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON)

st.title("🤖 Wiki Chatbot")
st.subheader("Learn things - random things!")

add_selectbox = st.sidebar.selectbox(
    "What kind of search?", ("Standard vector search", "HyDE")
)

if not openai.api_key and "OPENAI_API_KEY" not in os.environ:
    warning = st.sidebar.warning("""
    No API key provided. You can set your API key in code using 'openai.api_key = <API-KEY>', or you can set the environment variable OPENAI_API_KEY=<API-KEY>). 
    
    Else, please set your API key below.
    """)
    
    openai.api_key = st.sidebar.text_input("OpenAI API key", type="password")
    if openai.api_key:
        warning.empty()

msgs = StreamlitChatMessageHistory()
token_count = sum(len(str(i)) for i in msgs.messages)

if len(msgs.messages) == 0 or st.sidebar.button("Reset chat history") or token_count > 4097:
    clear_history(token_count)

avatars = {"human": "user", "ai": "assistant"}

for idx, msg in enumerate(msgs.messages):
    with st.chat_message(avatars[msg.type]):
        # Render intermediate steps if any were saved
        for step in st.session_state.steps.get(str(idx), []):
            if step[0].tool == "_Exception":
                continue
            with st.status(
                f"**{step[0].tool}**: {step[0].tool_input}", state="complete"
            ):
                st.write(step[0].log)
                st.write(step[1])
        st.write(msg.content)

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


if prompt := st.chat_input("What is light made of?"):
    st.chat_message("user").write(prompt)

    executor = initiate_agent(tools)

    with st.chat_message("assistant"):
        st_cb = StreamlitCallbackHandler(st.container(), max_thought_containers=1)
        try:
            response = executor(prompt, callbacks=[st_cb])
        except InvalidRequestError as e:
            clear_history(token_count)
            st.experimental_rerun()
        st.write(response["output"])
        st.session_state.steps[str(len(msgs.messages) - 1)] = response[
            "intermediate_steps"
        ]

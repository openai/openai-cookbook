import os

import openai
import streamlit as st
from assistant import (answer_question_hyde, answer_user_question, ask_gpt,
                       initiate_agent)
from database import get_redis_connection
from langchain.agents import Tool
from langchain.callbacks import StreamlitCallbackHandler
from langchain.memory.chat_message_histories import StreamlitChatMessageHistory
from openai.error import InvalidRequestError

# General settings
PAGE_TITLE, PAGE_ICON = "Knowledge Retrieval Bot", "🤖"
st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON)

st.title("🤖 Wiki Chatbot")
st.subheader("Learn things - random things!")

add_selectbox = st.sidebar.selectbox(
    "What kind of search?", ("Standard vector search", "HyDE")
)

# Authenticate OpenAI
if not openai.api_key and "OPENAI_API_KEY" not in os.environ:
    warning = st.sidebar.info(
        """
    No API key provided. You can set your API key in code using 
    'openai.api_key = <API-KEY>', or you can set the environment 
    variable `OPENAI_API_KEY=<API-KEY>`. Else, please set your API key below.
    """
    )
    openai.api_key = st.sidebar.text_input("OpenAI API key", type="password")
    if openai.api_key:
        warning.empty()

msgs = StreamlitChatMessageHistory()
token_count = sum(len(str(i)) for i in msgs.messages)


def clear_history(token_count):
    msgs.clear()
    message = (
        "How can I help you?"
        if token_count <= 4097
        else f"This model's maximum context length is 4097 tokens. Your messages resulted in {token_count} tokens. Resetting chat history."
    )
    msgs.add_ai_message(message)
    st.session_state.steps = {}


if not msgs.messages or st.sidebar.button("Reset chat history"):
    clear_history(token_count)

avatars = {"human": "user", "ai": "assistant"}

for idx, msg in enumerate(msgs.messages):
    with st.chat_message(avatars[msg.type]):
        # Render intermediate steps if any were saved
        for step in st.session_state.steps.get(str(idx), []):
            if step[0].tool != "_Exception":
                with st.status(
                    f"**{step[0].tool}**: {step[0].tool_input}", state="complete"
                ):
                    st.write(step[0].log, step[1])
        st.write(msg.content)

# Define which tools the agent can use to answer user queries
tools = [
    Tool(
        name="Search",
        func=answer_user_question
        if add_selectbox == "Standard vector search"
        else answer_question_hyde,
        description="Answer general knowledge questions.",
    ),
    Tool(
        name="Ask", func=ask_gpt, description="Answer non-general knowledge questions."
    ),
]

if prompt := st.chat_input(
    "Examples: What is light made of? When was Wikipedia founded?"
):
    st.chat_message("user").write(prompt)
    executor = initiate_agent(tools)
    with st.chat_message("assistant"):
        st_cb = StreamlitCallbackHandler(st.container())
        try:
            response = executor(prompt, callbacks=[st_cb])
        except InvalidRequestError as e:
            clear_history(token_count)
            st.experimental_rerun()
        st.write(response["output"])
        st.session_state.steps[str(len(msgs.messages) - 1)] = response[
            "intermediate_steps"
        ]

import os
import re
from typing import List, Union

import openai
import streamlit as st
from config import CHAT_MODEL, INDEX_NAME, RETRIEVAL_PROMPT, SYSTEM_PROMPT
from database import get_redis_connection, get_redis_results
from langchain import LLMChain, SerpAPIWrapper
from langchain.agents import (AgentExecutor, AgentOutputParser, AgentType,
                              LLMSingleActionAgent, Tool)
from langchain.chat_models import ChatOpenAI
from langchain.memory import (ConversationBufferMemory,
                              ConversationBufferWindowMemory)
from langchain.memory.chat_message_histories import StreamlitChatMessageHistory
from langchain.prompts import BaseChatPromptTemplate
from langchain.schema import AgentAction, AgentFinish, HumanMessage

redis_client = get_redis_connection()


def answer_user_question(query):

    results = get_redis_results(redis_client, query, INDEX_NAME)

    results.to_csv("results.csv")

    search_content = ""
    for x, y in results.head(3).iterrows():
        search_content += y["title"] + "\n" + y["result"] + "\n\n"

    retrieval_prepped = RETRIEVAL_PROMPT.format(
        SEARCH_QUERY_HERE=query, SEARCH_CONTENT_HERE=search_content
    )

    retrieval = openai.ChatCompletion.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": retrieval_prepped}],
        max_tokens=500,
    )

    # Response provided by GPT-3.5
    return retrieval["choices"][0]["message"]["content"]


def answer_question_hyde(query):

    hyde_prompt = """You are OracleGPT, an helpful expert who answers user questions to the best of their ability.
    Provide a confident answer to their question. If you don't know the answer, make the best guess you can based on the context of the question.

    User question: {USER_QUESTION_HERE}
    
    Answer:"""

    hypothetical_answer = openai.ChatCompletion.create(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "user",
                "content": hyde_prompt.format(USER_QUESTION_HERE=query),
            }
        ],
    )["choices"][0]["message"]["content"]
    # st.write(hypothetical_answer)
    results = get_redis_results(redis_client, hypothetical_answer, INDEX_NAME)

    results.to_csv("results.csv")

    search_content = ""
    for x, y in results.head(3).iterrows():
        search_content += y["title"] + "\n" + y["result"] + "\n\n"

    retrieval_prepped = RETRIEVAL_PROMPT.replace("SEARCH_QUERY_HERE", query).replace(
        "SEARCH_CONTENT_HERE", search_content
    )
    retrieval = openai.ChatCompletion.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": retrieval_prepped}],
        max_tokens=500,
    )

    return retrieval["choices"][0]["message"]["content"]


# Set up a prompt template
class CustomPromptTemplate(BaseChatPromptTemplate):
    # The template to use
    template: str
    # The list of tools available
    tools: List[Tool]

    def format_messages(self, **kwargs) -> str:
        # Get the intermediate steps (AgentAction, Observation tuples)
        # Format them in a particular way
        intermediate_steps = kwargs.pop("intermediate_steps")
        thoughts = ""
        for action, observation in intermediate_steps:
            thoughts += action.log
            thoughts += f"\nObservation: {observation}\nThought: "
        # Set the agent_scratchpad variable to that value
        kwargs["agent_scratchpad"] = thoughts
        # Create a tools variable from the list of tools provided
        kwargs["tools"] = "\n".join(
            [f"{tool.name}: {tool.description}" for tool in self.tools]
        )
        # Create a list of tool names for the tools provided
        kwargs["tool_names"] = ", ".join([tool.name for tool in self.tools])
        formatted = self.template.format(**kwargs)
        return [HumanMessage(content=formatted)]


class CustomOutputParser(AgentOutputParser):
    def parse(self, llm_output: str) -> Union[AgentAction, AgentFinish]:
        # Check if agent should finish
        if "Final Answer:"  in llm_output:
            return AgentFinish(
                # Return values is generally always a dictionary with a single `output` key
                # It is not recommended to try anything else at the moment :)
                return_values={"output": llm_output.split("Final Answer:")[-1].strip()},
                log=llm_output,
            )
        # Parse out the action and action input
        regex = r"Action\s*\d*\s*:(.*?)\nAction\s*\d*\s*Input\s*\d*\s*:[\s]*(.*)"
        match = re.search(regex, llm_output, re.DOTALL)
        if not match:
            return AgentAction(tool="Ask", tool_input=llm_output, log=llm_output)
        action = match.group(1).strip()
        action_input = match.group(2)
        # Return the action and action input
        return AgentAction(
            tool=action, tool_input=action_input.strip(" ").strip('"'), log=llm_output
        )


def initiate_agent(tools):
    prompt = CustomPromptTemplate(
        template=SYSTEM_PROMPT,
        tools=tools,
        # This omits the `agent_scratchpad`, `tools`, and `tool_names` variables because those are generated dynamically
        # The history template includes "history" as an input variable so we can interpolate it into the prompt
        input_variables=["input", "intermediate_steps", "history"],
    )

    # Initiate the memory with k=2 to keep the last two turns
    # Provide the memory to the agent
    # memory = ConversationBufferWindowMemory(k=2)
    msgs = StreamlitChatMessageHistory()
    memory = ConversationBufferMemory(
        chat_memory=msgs,
        return_messages=True,
        memory_key="history",
        output_key="output",
    )

    output_parser = CustomOutputParser()

    if not openai.api_key and not os.environ.get("OPENAI_API_KEY"):
        warning = st.sidebar.warning("""
        No API key provided. You can set your API key in code using 'openai.api_key = <API-KEY>', or you can set the environment variable OPENAI_API_KEY=<API-KEY>). 
        
        Else, please set your API key below.
        """)
        
        openai.api_key = st.sidebar.text_input("OpenAI API key", type="password")
        if openai.api_key is not None:
            warning.empty()

    llm = ChatOpenAI(
        temperature=0,
        openai_api_key=openai.api_key,
    )

    # LLM chain consisting of the LLM and a prompt
    llm_chain = LLMChain(llm=llm, prompt=prompt)

    tool_names = [tool.name for tool in tools]
    agent = LLMSingleActionAgent(
        llm_chain=llm_chain,
        output_parser=output_parser,
        stop=["\nObservation:"],
        allowed_tools=tool_names,
    )

    agent_executor = AgentExecutor.from_agent_and_tools(
        agent=agent,
        tools=tools,
        memory=memory,
        return_intermediate_steps=True,
        handle_parsing_errors=True,
        max_iterations=10,
        verbose=True,
        max_execution_time=60,
    )

    return agent_executor


def ask_gpt(query):
    response = openai.ChatCompletion.create(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "user",
                "content": "Please answer my question.\nQuestion: {}".format(query),
            }
        ],
        temperature=0,
    )
    return response["choices"][0]["message"]["content"]

# Re-initialize the agent with our new list of tools
prompt_with_history = CustomPromptTemplate(
    template=template_with_history,
    tools=expanded_tools,
    input_variables=["input", "intermediate_steps", "history"]
)
llm_chain = LLMChain(llm=llm, prompt=prompt_with_history)
multi_tool_names = [tool.name for tool in expanded_tools]
multi_tool_agent = LLMSingleActionAgent(
    llm_chain=llm_chain, 
    output_parser=output_parser,
    stop=["\nObservation:"], 
    allowed_tools=multi_tool_names
)
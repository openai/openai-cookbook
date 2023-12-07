multi_tool_memory = ConversationBufferWindowMemory(k=2)
multi_tool_executor = AgentExecutor.from_agent_and_tools(agent=multi_tool_agent, tools=expanded_tools, verbose=True, memory=multi_tool_memory)
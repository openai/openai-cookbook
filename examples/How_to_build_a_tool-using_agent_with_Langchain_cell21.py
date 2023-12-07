# Initiate the memory with k=2 to keep the last two turns
# Provide the memory to the agent
memory = ConversationBufferWindowMemory(k=2)
agent_executor = AgentExecutor.from_agent_and_tools(agent=agent, tools=tools, verbose=True, memory=memory)
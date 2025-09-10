import asyncio
import os
# Instructions: 
# KUMO_API_KEY and OPENAI_API_KEY need to be set as environment variables
# export KUMO_API_KEY='your-kumo-api-key-here'
# export OPENAI_API_KEY='your-openai-api-key-here'

from datetime import datetime, timedelta
from typing import List, Dict

from agents import Agent, Runner, gen_trace_id, trace, handoff
from agents.mcp import MCPServer, MCPServerStdio, ToolFilterContext
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

# Insurance Data Configuration
DATA_DIR = "s3://kumo-sdk-public/rfm-datasets/insurance/"
# FILE_NAMES = ["agents.csv", "policies.csv", "customers.csv", "pets.csv", 
#               "products.csv", "properties.csv", "vehicles.csv"]
FILE_NAMES = ["agents.csv", "policies.csv", "customers.csv", "products.csv"] # simpler example
# FILE_NAMES = ["customers.csv", "pets.csv"] # failing example (not enough data)

# Sample customer IDs with policies expiring in next 30 days
# EXPIRING_CUSTOMER_IDS = [13, 402, 14, 329, 375, 239, 493, 319]
EXPIRING_CUSTOMER_IDS = [13, 402, 14] # shorter example


def get_expiring_customers() -> List[int]:
    """
    Get customer IDs with policies expiring in the next 30 days.
    """
    print(f"🔍 Found {len(EXPIRING_CUSTOMER_IDS)} customers with policies expiring in next 30 days")
    print(f"📋 Customer IDs: {EXPIRING_CUSTOMER_IDS}")
    return EXPIRING_CUSTOMER_IDS


def dynamic_tool_filter(context: ToolFilterContext, tool) -> bool:
    """
    Dynamic tool filtering based on agent context.
    Each agent gets only the tools they need for their specific role.
    """
    agent_name = context.agent.name
    tool_name = tool.name
    
    # Define tool access patterns for each agent
    agent_tool_mapping = {
        "Assessment Agent": {
            "get_docs",
            "inspect_table_files",
        },
        "Prediction Agent": {
            "get_docs",
            "inspect_table_files",
            "inspect_graph_metadata",
            "update_graph_metadata",
            "materialize_graph",
            "predict",
        },
        "Business Action Agent": {
            "lookup_table_rows",
            "inspect_graph_metadata",
        },
        "Predictive Insurance Orchestrator": {
        }
    }
    
    allowed_tools = agent_tool_mapping.get(agent_name, set())
    is_allowed = tool_name in allowed_tools
    
    return is_allowed

async def setup_predictive_agents(mcp_server: MCPServer):
    """
    Initialize the predictive agent architecture with handoffs and tool filtering.
    """
    
    # Assessment Agent - Determines prediction feasibility
    assessment_agent = Agent(
        name="Assessment Agent",
        model="gpt-5",
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
        
        You are an expert data analyst who assesses whether predictive 
        tasks are feasible given available data.
        
        Your responsibilities:
        1. Use the `get_docs` tool to understand KumoRFM capabilities, data requrements, and pql syntax
        2. Use the `inspect_table_files` tool to understand the data in the files
        3. Determine if the data is sufficient to answer the business request(s)
        
        Be specific about what predictions are possible and why. If data is insufficient,
        explain exactly what's missing and what would be needed. For predictions that are possible provide 
        predictive queries that can be used to answer the business request(s).
        
        After completing your assessment, hand off back to the Orchestrator with your findings
        and recommendations for next steps.""",
        mcp_servers=[mcp_server]
    )

    # Prediction Agent - Sets up data and executes predictions
    prediction_agent = Agent(
        name="Prediction Agent", 
        model="gpt-5",
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
        
        You are a comprehensive prediction specialist who handles both 
        data preparation and prediction execution using KumoRFM.

        Your responsibilities:
        1. Use the `get_docs` tool to understand KumoRFM capabilities, data requrements, and pql syntax
        2. Use the `inspect_graph_metadata` tool to see if a suitable graph already exists for the requested predictions
        3. Use the `inspect_table_files` tool to understand the data in the files if needed to answer the business request(s)
        4. Use the `update_graph_metadata` tool to update the graph metadata if needed
        5. Use the `materialize_graph` tool to materialize the graph
        6. Use the `predict` tool to execute the predictions
        7. Summarize the key prediction results in a structured format

        After completing predictions successfully, hand off back to the Orchestrator
        with your prediction results and analysis. If the predictions are not possible,
        explain why and hand off back to the Orchestrator with your findings and recommendations.""",
        mcp_servers=[mcp_server]
    )

    # Business Action Agent - Converts predictions to business actions
    action_agent = Agent(
        name="Business Action Agent", 
        model="gpt-5",
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
        
        You are a business operations specialist who converts 
        prediction results into actionable business communications.

        Your responsibilities:
        1. Take the User Request and understand the business intent
        2. Use the results provided by the Prediction Agent to create a personalized business communication and/or recommendations

        Think about the prediction results and what they mean in the context of the insurance business. You can write an email, with recommendation + discount offer, to the user
        if you see a high risk of churn and good opportunity to cross-sell.
        
        After creating the business actions, return the results to the Orchestrator.""",
        mcp_servers=[mcp_server]
    )
    
    # Orchestrator Agent - Manages the overall workflow
    orchestrator_agent = Agent(
        name="Predictive Insurance Orchestrator",
        model="gpt-5",
        instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
        
        You are the orchestrator for predictive insurance workflows. Your role is to:
        
        1. Understand the business request and context
        2. Coordinate with specialized agents to fulfill the request
        3. Ensure the workflow progresses logically through assessment → prediction → action
        4. Provide status updates and manage the overall process
        
        Available context:
        - Data location: {DATA_DIR}
        - Available files: {', '.join(FILE_NAMES)}
        - Sample expiring customer IDs: {EXPIRING_CUSTOMER_IDS}
        
        Workflow:
        1. For prediction requests, start by handing off to the Assessment Agent
        2. When Assessment Agent returns, evaluate their findings and decide next steps:
           - If feasible, hand off to Prediction Agent
           - If not feasible, provide alternative recommendations
        3. When Prediction Agent returns with results, hand off to Business Action Agent
        4. When Business Action Agent returns, compile and present final results
        
        Each sub-agent will return to you with their results. Coordinate the workflow
        by deciding which agent to involve next based on the current state and results. 
        
        Make sure to hand off to the next agent with the results of the previous agent.""",
        mcp_servers=[mcp_server],
        handoffs=[handoff(assessment_agent), handoff(prediction_agent), handoff(action_agent)]
    )
    
    # Configure handoffs
    assessment_agent.handoffs = [handoff(orchestrator_agent,)]
    prediction_agent.handoffs = [handoff(orchestrator_agent)]
    action_agent.handoffs = [handoff(orchestrator_agent)]
    
    return orchestrator_agent, assessment_agent, prediction_agent, action_agent


async def run_predictive_workflow(mcp_server: MCPServer, user_request: str):
    """
    Run the predictive workflow using the orchestrator agent with handoffs
    """
    
    # Initialize agents
    orchestrator_agent, assessment_agent, prediction_agent, action_agent = await setup_predictive_agents(mcp_server)
    
    print("🏢 Starting Predictive Insurance Workflow")
    print("=" * 60)
    
    # Create comprehensive request for orchestrator
    orchestrator_request = f"""
    Handle this predictive insurance business request:
    
    "{user_request}"
    
    Context:
    - Available data: {DATA_DIR} with files {FILE_NAMES}
    - Customers with expiring policies: {EXPIRING_CUSTOMER_IDS}
    
    Please coordinate the complete workflow:
    1. Assess the feasibility of the requested predictions
    2. Set up the data graph and execute predictions if feasible
    3. Generate actionable business communications and recommendations
    
    Use handoffs to specialized agents as appropriate to ensure each step is handled by the right expert.
    """
    
    # Execute the workflow
    result = await Runner.run(
        starting_agent=orchestrator_agent,
        input=orchestrator_request,
        max_turns=25
    )
    
    print("=" * 60)
    print("🎉 Workflow Complete!")
    print("✅ Insurance retention and cross-selling analysis finished")
    
    return result


async def main():
    """
    Main function for the predictive insurance workflow
    """
    print("🏢 Predictive Insurance Agent")
    print("🎯 Customer Retention & Cross-Selling Analysis")
    print()
    
    # Business request in natural language
    user_request = """
    I need to identify customers whose insurance policies are expiring in the next 30 days 
    and are at risk of not renewing. For high-risk customers, I want to:
    
    1. Predict their likelihood of churning 
    2. Recommend additional insurance products they might purchase
    3. Generate personalized retention emails with discount offers and product bundles
    
    The goal is to proactively retain customers and increase cross-selling.
    """
    
    # Get expiring customers
    expiring_customers = get_expiring_customers()
    
    # Environment setup
    kumo_api_key = os.getenv("KUMO_API_KEY")
    if not kumo_api_key:
        print("❌ KUMO_API_KEY environment variable not set")
        print("📝 Please set your KumoRFM API key: export KUMO_API_KEY='your-key-here'")
        return
    
    print("🔌 Connecting to KumoRFM...")
    
    # try:
    async with MCPServerStdio(
        name="KumoRFM Server",
        params={
            "command": "python", 
            "args": ["-m", "kumo_rfm_mcp.server"],
            "env": {
                "KUMO_API_KEY": kumo_api_key,
                "KUMO_API_URL": "https://kumorfm.ai/api"
            }
        },
        tool_filter=dynamic_tool_filter
    ) as server:
        
        # Enable tracing
        trace_id = gen_trace_id()
        with trace(workflow_name="Predictive Insurance Workflow", trace_id=trace_id):
            print(f"📊 View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}\n")
            print("✅ Connected to KumoRFM successfully!")
            print()
            
            # Execute the workflow
            results = await run_predictive_workflow(server, user_request)
            
            print("\n📋 RESULTS:")
            print("=" * 40)
            print(results)
            print("=" * 40)
            
            return results


if __name__ == "__main__":
    asyncio.run(main())
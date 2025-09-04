# Predictive Insurance Agent

Multi-agent system that predicts customer churn and generates retention strategies using KumoRFM and OpenAI's Agents SDK.

## What it does

Analyzes insurance customers with expiring policies to:
- Predict churn risk
- Recommend additional products  
- Generate personalized retention emails

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set API keys**:
   ```bash
   export KUMO_API_KEY='your-kumo-api-key-here'
   export OPENAI_API_KEY='your-openai-api-key-here'
   ```

## Run

```bash
python predictive_insurance_agent.py
```

## How it works

Three specialized agents work together:
- **Assessment Agent**: Checks if predictions are possible with available data
- **Prediction Agent**: Runs ML models to predict churn and recommend products
- **Business Action Agent**: Creates personalized emails and business recommendations

An orchestrator coordinates the agents using handoffs for a seamless workflow.
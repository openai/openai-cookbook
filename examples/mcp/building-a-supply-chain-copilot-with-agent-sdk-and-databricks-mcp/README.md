# Databricks MCP Assistant (with React UI)

A full-stack, Databricks-themed conversational assistant for supply chain queries, powered by OpenAI Agents and Databricks MCP servers. Includes a React chat UI and a FastAPI backend that streams agent responses.

---

## Features
- Conversational chat UI (React) with Databricks red palette
- FastAPI backend with streaming `/chat` endpoint
- Secure Databricks MCP integration 
- Example agent logic and tool usage
- Modern UX, easy local development


## Quickstart

### 0. Databricks assets

You can kick start your project with Databricks’ Supply-Chain Optimization Solution Accelerator (or any other accelerator if working in a different industry). Clone this accelerator’s GitHub repo into your Databricks workspace and run the bundled notebooks by running notebook 1:

https://github.com/lara-openai/databricks-supply-chain

These notebooks stand up every asset the Agent will later reach via MCP, from raw enterprise tables and unstructured e-mails to classical ML models and graph workloads.

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- Databricks credentials in `~/.databrickscfg`
- OpenAI API key 
- (Optional) Virtualenv/pyenv for Python isolation

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 3. Start the Backend (FastAPI)

To kick off the backend, run:

```bash
python -m uvicorn api_server:app --reload --port 8000
```
- The API will be available at http://localhost:8000
- FastAPI docs: http://localhost:8000/docs

### 4. Start the Frontend (React UI)
In a different terminal, run the following:
```bash
cd ui
npm install
npm run dev
```
- The app will be available at http://localhost:5173

---

## Usage
1. Open [http://localhost:5173](http://localhost:5173) in your browser.
2. Type a supply chain question (e.g., "What are the delays with distribution center 5?") and hit Send.
3. The agent will stream back a response from the Databricks MCP server.

---

## Troubleshooting
- **Port already in use:** Kill old processes with `lsof -ti:8000 | xargs kill -9` (for backend) or change the port.
- **Frontend not loading:** Make sure you ran `npm install` and `npm run dev` in the `ui/` folder.

---

## Customization
- To change the agent's greeting, edit `ui/src/components/ChatUI.jsx`.
- To update backend agent logic, modify `api_server.py`.
- UI styling is in `ui/src/components/ChatUI.css` (Databricks red palette).




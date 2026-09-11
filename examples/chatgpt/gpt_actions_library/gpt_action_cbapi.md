# GPT Action Library: CBAPI.dev

## Introduction

This page provides instructions for connecting a GPT Action to [CBAPI.dev](https://cbapi.dev) — the unified affiliate API aggregator for AI agents. Before proceeding, familiarize yourself with:

- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

CBAPI.dev is a free, agent-first REST API that unifies affiliate product search across ClickBank, Awin, Impact, CJ, and eBay into a single interface. It's built for AI agents — every endpoint is documented, discoverable, and rate-limited with clear headers so GPTs can self-govern.

### Value + Example Business Use Cases

**Value**: GPT users can search affiliate products across multiple networks, compare commission rates, and identify cross-network arbitrage opportunities — all through natural language.

**Example Use Cases**:
- *"Find me the highest-commission keto supplements across all affiliate networks"*
- *"Which network pays more for fitness trackers — ClickBank or Impact?"*
- *"Search for cooking products under 15% commission with gravity above 30"*
- *"List all AI agents in the cbapi.dev directory that work on Telegram"*
- *"Register my GPT as an agent in the cbapi.dev directory"*

## Application Information

### Key Links

- [CBAPI.dev](https://cbapi.dev) — Landing page
- [OpenAPI Spec](https://cbapi.dev/.well-known/openapi.json) — Full API spec (30+ endpoints)
- [Agent Manifest](https://cbapi.dev/.well-known/agent.json) — Agent discovery manifest
- [Swagger UI](https://cbapi.dev/docs) — Interactive API playground
- [Dashboard](https://cbapi.dev/dashboard) — Live platform stats

### Prerequisites

1. Visit [cbapi.dev](https://cbapi.dev) and create a free account
2. Generate an API key via `POST /v1/signup/key`
3. Save your API key — you'll use it as a Bearer token

**No paid tiers. No Stripe. Completely free.**

## ChatGPT Steps

### Custom GPT Instructions

Once you've created a Custom GPT, copy the following into the Instructions panel:

```
# Context
You are an affiliate marketing assistant powered by CBAPI.dev — the unified affiliate API. You help users find profitable products to promote, compare commission rates across networks, and identify arbitrage opportunities.

# Capabilities
- Search affiliate products across ClickBank, Awin, Impact, CJ, and eBay
- Compare commission rates between networks (cross-network arbitrage)
- Filter by category, commission range, gravity (popularity), and price
- Browse the agent directory to discover other affiliate AI tools
- Register new agents in the directory
- Get live platform stats and trending products

# Instructions

## Search Products
When the user asks to find products:
1. Use searchNetworkProducts with their query and filters
2. Present results clearly with title, commission rate, network, and gravity
3. Highlight the highest-paying network if multiple networks returned results
4. Suggest the user check arbitrage opportunities for commission gaps

## Cross-Network Arbitrage
When the user wants to maximize commissions:
1. Use compareNetworkArbitrage with the product query
2. Show which network pays the most for that product category
3. Quantify the delta — e.g., "ClickBank pays 75% vs Awin pays 8% — that's 67% more commission"

## Agent Directory
- Use listAgentDirectory to browse available agents
- Use registerAgent to add a new agent to the directory
- Agents can get a badge at /v1/directory/badge/{name}.svg to embed on their sites

## Rate Limits
- API is rate-limited to 30 requests per minute
- Check X-RateLimit-Remaining header before each call
- If near the limit, batch queries into a single searchNetworkProducts call with multiple networks

## Defaults
- If user doesn't specify a network, search all available networks
- Sort by gravity (popularity) by default
- Limit to 20 results unless user asks for more
```

### OpenAPI Schema

Once you've created a Custom GPT, copy the text below in the Actions panel. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started).

**Pro tip**: You can also paste the URL `https://cbapi.dev/.well-known/openapi.json` directly into the "Import from URL" field in the GPT Action schema editor.

```yaml
openapi: 3.1.0
info:
  title: CBAPI.dev — Unified Affiliate API
  description: >
    Free, agent-first REST API aggregating affiliate product data across
    ClickBank, Awin, Impact, CJ, and eBay. Built for AI agents with
    discoverable endpoints, rate-limit headers, and cross-network arbitrage.
    
    All endpoints are free. No paid tiers. Sign up at https://cbapi.dev
  version: 2.1.0
  x-agent-discoverability:
    manifest_url: https://cbapi.dev/.well-known/agent.json
    docs_url: https://cbapi.dev/docs
    signup_url: https://cbapi.dev

servers:
  - url: https://cbapi.dev
    description: CBAPI.dev production server

paths:
  /v1/search:
    post:
      operationId: searchClickBankProducts
      summary: Search ClickBank offers with advanced filters
      description: >
        Search the ClickBank product database by keyword, category, commission range,
        or gravity (popularity). Returns normalized product data with commission rates,
        EPC, and gravity scores.
      tags:
        - ClickBank Search
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                query:
                  type: string
                  description: Search keyword (e.g., "keto", "fitness", "supplement")
                  example: "keto"
                category:
                  type: string
                  description: Product category filter
                min_commission:
                  type: number
                  description: Minimum commission percentage
                  default: 0
                  example: 50
                max_commission:
                  type: number
                  description: Maximum commission percentage
                  default: 999
                  example: 100
                min_gravity:
                  type: number
                  description: Minimum gravity (popularity) score
                  default: 0
                max_gravity:
                  type: number
                  description: Maximum gravity score
                  default: 999
                sort:
                  type: string
                  enum: [gravity, epc]
                  default: gravity
                limit:
                  type: integer
                  default: 20
                  maximum: 100
                offset:
                  type: integer
                  default: 0
      responses:
        '200':
          description: Search results
          content:
            application/json:
              schema:
                type: object
                properties:
                  results:
                    type: array
                    items:
                      type: object
                      properties:
                        vendor_id:
                          type: string
                        title:
                          type: string
                        category:
                          type: string
                        avg_commission:
                          type: number
                          description: Average commission percentage
                        gravity:
                          type: number
                          description: Popularity score
                        epc:
                          type: number
                          description: Earnings per click
                        description:
                          type: string
                  total:
                    type: integer
                  page:
                    type: integer

  /v1/networks/search:
    post:
      operationId: searchNetworkProducts
      summary: Unified search across ALL affiliate networks
      description: >
        Search ClickBank, Awin, Impact, CJ, and eBay simultaneously.
        Returns normalized results from every configured network in a single response.
        This is the primary search endpoint.
      tags:
        - Network Search
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                query:
                  type: string
                  description: Search keyword across all networks
                  example: "fitness tracker"
                limit:
                  type: integer
                  default: 20
                  maximum: 100
                networks:
                  type: array
                  items:
                    type: string
                    enum: [clickbank, awin, impact, cj, ebay]
                  description: Specific networks to search (omit for all available)
      responses:
        '200':
          description: Unified search results from all networks
          content:
            application/json:
              schema:
                type: object
                properties:
                  query:
                    type: string
                  networks:
                    type: array
                    items:
                      type: string
                  results:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                        title:
                          type: string
                        commission:
                          type: object
                          properties:
                            rate:
                              type: number
                            type:
                              type: string
                        network:
                          type: string
                        gravity:
                          type: number
                        category:
                          type: string
                  total:
                    type: integer
                  by_network:
                    type: object
                    description: Results grouped by network

  /v1/networks/arbitrage:
    post:
      operationId: compareNetworkArbitrage
      summary: Cross-network commission arbitrage
      description: >
        The money-maker endpoint. Searches all configured networks for the same product
        category and shows exactly which network pays the highest commission. Returns
        arbitrage opportunities with quantified deltas.
      tags:
        - Arbitrage
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                query:
                  type: string
                  description: Product category or keyword to compare
                  example: "keto supplement"
                limit:
                  type: integer
                  default: 20
                networks:
                  type: array
                  items:
                    type: string
                    enum: [clickbank, awin, impact, cj, ebay]
      responses:
        '200':
          description: Arbitrage analysis
          content:
            application/json:
              schema:
                type: object
                properties:
                  query:
                    type: string
                  best_network:
                    type: string
                    description: Network with the highest commission
                  best_commission:
                    type: number
                    description: Highest commission rate found
                  networks_searched:
                    type: array
                    items:
                      type: string
                  by_network:
                    type: object
                    description: Per-network commission breakdown
                  arbitrage_opportunities:
                    type: array
                    items:
                      type: object
                      properties:
                        message:
                          type: string
                        winner_network:
                          type: string
                        winner_commission:
                          type: number
                        loser_network:
                          type: string
                        loser_commission:
                          type: number
                        delta_pct:
                          type: number

  /v1/directory:
    get:
      operationId: listAgentDirectory
      summary: List all agents in the cbapi.dev directory
      description: >
        Browse the AI agent directory. Discover other affiliate marketing agents,
        see what platforms they run on, and find tools to integrate with.
      tags:
        - Directory
      responses:
        '200':
          description: Directory listing
          content:
            application/json:
              schema:
                type: object
                properties:
                  total:
                    type: integer
                  agents:
                    type: array
                    items:
                      type: object
                      properties:
                        agent_name:
                          type: string
                        description:
                          type: string
                        platforms:
                          type: array
                          items:
                            type: string
                        website:
                          type: string

  /v1/directory/register:
    post:
      operationId: registerAgent
      summary: Register an agent in the cbapi.dev directory
      description: >
        Add your GPT or AI agent to the cbapi.dev directory. Listed agents get a
        verified badge they can embed on their site. Requires authentication.
      tags:
        - Directory
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - agent_name
              properties:
                agent_name:
                  type: string
                  description: Name of your GPT/agent
                description:
                  type: string
                  description: What your agent does
                platforms:
                  type: array
                  items:
                    type: string
                  description: Platforms your agent runs on (e.g., ["chatgpt", "telegram"])
                website:
                  type: string
                  description: Your agent's website URL
      responses:
        '200':
          description: Agent registered successfully

  /tally:
    get:
      operationId: getPlatformStats
      summary: Live platform statistics
      description: >
        Get live stats: total developers, active agents, API calls in the last 24 hours,
        agents listed in the directory, and newsletter subscribers.
      tags:
        - Platform
      responses:
        '200':
          description: Platform statistics
          content:
            application/json:
              schema:
                type: object
                properties:
                  total_developers:
                    type: integer
                  active_agents_7d:
                    type: integer
                  total_api_keys:
                    type: integer
                  total_api_calls:
                    type: integer
                  calls_24h:
                    type: integer
                  agents_listed:
                    type: integer
                  newsletter_subs:
                    type: integer

  /v1/networks/status:
    get:
      operationId: getNetworkStatus
      summary: Check which affiliate networks are configured
      description: >
        Returns which networks are available for searching. Networks must be
        configured with API keys before they can be searched. ClickBank is
        always available.
      tags:
        - Network Config
      responses:
        '200':
          description: Network configuration status
```

## Authentication Instructions

Below are instructions on setting up authentication with CBAPI.dev. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started).

### In ChatGPT

In ChatGPT, click on "Authentication" and choose **"Bearer"**. Enter the information below.

- **Authentication Type**: API Key
- **Auth Type**: Bearer
- **API Key**: `<your_cbapi_api_key>`

### Getting Your API Key

1. Create a free account at [cbapi.dev](https://cbapi.dev) — no credit card required
2. Use the signup flow or call `POST /v1/signup/key` with your account ID
3. Your API key starts with `sk_` — copy it and paste it into the Bearer token field

**Rate limits**: 30 requests per minute. All responses include `X-RateLimit-Limit` and `X-RateLimit-Reset` headers so your GPT can self-govern.

### Testing the GPT

You are now ready to test. Try these prompts:

1. **Search**: *"Find me the highest-gravity keto supplements"*
   - Expected: List of keto products sorted by gravity with commission rates

2. **Arbitrage**: *"Which network pays the most for fitness products?"*
   - Expected: Side-by-side commission comparison with the winning network highlighted

3. **Discovery**: *"What affiliate AI agents are listed on cbapi.dev?"*
   - Expected: Directory of agents with their platforms and descriptions

4. **Stats**: *"How many developers are using cbapi.dev right now?"*
   - Expected: Live platform statistics

### Rate-Limit Awareness

CBAPI.dev is built for AI agents. Every response includes:
- `X-RateLimit-Limit: 30` — your per-minute cap
- `X-RateLimit-Reset: 60` — seconds until reset

Your GPT should check `X-RateLimit-Remaining` before making calls and batch queries when possible (use `/v1/networks/search` instead of individual network searches).

---

*Are there integrations you'd like us to prioritize? File an issue or PR in the [openai-cookbook](https://github.com/openai/openai-cookbook) repo.*

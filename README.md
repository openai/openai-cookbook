# 🚀 CEO Assistant - LLM Agent for SaaS B2B Leadership

An intelligent AI assistant specifically designed for SaaS B2B CEOs, built using OpenAI's LLM agents and integrated with your business tools (HubSpot, Mixpanel, etc.).

## 🎯 Overview

This CEO Assistant is designed to help you accelerate growth at Colppy.com by providing:

- **Strategic Planning**: Market analysis, competitive intelligence, growth opportunities
- **Operational Intelligence**: KPI monitoring, team performance insights, weekly reports
- **Communication Support**: Board presentations, stakeholder updates, meeting preparation
- **Data Integration**: Real-time insights from HubSpot, Mixpanel, and other business tools

## 🏗 Architecture

The assistant uses a multi-agent architecture with specialized agents:

```
CEO Assistant
├── Strategic Planning Agent    # Growth strategy & market analysis
├── Operational Intelligence   # KPIs, team performance, reports
├── Communication Agent        # Presentations, updates, meetings
└── Integration Layer         # HubSpot, Mixpanel, other APIs
```

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.8+
- OpenAI API key
- HubSpot API key (optional but recommended)
- Mixpanel credentials (optional but recommended)

### 2. Installation

```bash
# Clone or navigate to the project
cd /Users/virulana/openai-cookbook

# Create virtual environment
python -m venv ceo_assistant_env
source ceo_assistant_env/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file:

```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here

# Optional but recommended
HUBSPOT_API_KEY=your_hubspot_api_key_here
MIXPANEL_PROJECT_ID=your_mixpanel_project_id_here
MIXPANEL_API_SECRET=your_mixpanel_api_secret_here

# Meta Ads API (for campaign analysis)
META_ADS_ACCESS_TOKEN=your_meta_ads_access_token_here
META_ADS_ACCOUNT_ID=act_111192969640236
META_ADS_APP_ID=4098296043769963
META_ADS_APP_SECRET=your_meta_ads_app_secret_here
META_ADS_BUSINESS_ID=632964907150647
```

### 4. Run the Assistant

**Command Line Interface:**
```bash
python ceo_assistant_starter.py
```

**Web Interface:**
```bash
streamlit run ceo_assistant_app.py
```

## 📊 Features

### Strategic Planning Agent
- **Growth Opportunity Analysis**: Identifies top growth opportunities based on current metrics
- **Market Intelligence**: Competitive analysis and market positioning insights
- **Product Roadmap Support**: Data-driven product development recommendations
- **Argentina Market Focus**: Localized insights for the Argentina SaaS market

### Operational Intelligence Agent
- **Weekly Reports**: Automated operational intelligence summaries
- **KPI Monitoring**: Real-time tracking of key performance indicators
- **Team Performance**: Insights into team productivity and culture alignment
- **Process Optimization**: Recommendations for operational improvements

### Communication Agent
- **Board Presentations**: Automated board meeting content preparation
- **Stakeholder Updates**: Professional communication drafts
- **Meeting Preparation**: Agenda creation and talking points
- **Strategic Messaging**: Data-driven communication strategies

## 🔧 Customization for Colppy

### HubSpot Integration
The assistant connects to your HubSpot CRM to analyze:
- Customer acquisition metrics
- Sales pipeline performance
- Customer lifetime value
- Churn analysis
- **Monthly PQL Analysis** - Automated Product Qualified Lead tracking with standardized metrics

### Mixpanel Integration
Product analytics integration provides:
- User engagement metrics
- Feature adoption rates
- Conversion funnel analysis
- Retention insights

### Argentina Market Context
The assistant is configured with:
- Local market understanding
- SaaS B2B best practices for SMBs
- Accountant channel considerations
- Regional competitive landscape

## 📈 Use Cases

### Daily Operations
- **Morning Briefing**: "Give me today's key metrics and priorities"
- **Team Check-in**: "How is team performance this week?"
- **Customer Health**: "What customers need attention?"

### Strategic Planning
- **Growth Analysis**: "What are our top 3 growth opportunities?"
- **Market Research**: "Analyze our competitive position"
- **Product Strategy**: "What features should we prioritize?"

### Communication
- **Board Prep**: "Prepare next board meeting presentation"
- **Investor Updates**: "Draft quarterly investor update"
- **Team Communication**: "Create all-hands meeting agenda"

## 🎓 Learning Path

### Week 1: Foundation
1. **Study Agent Architecture**
   - Review `ceo_assistant_learning_guide.md`
   - Explore OpenAI Cookbook examples
   - Understand multi-agent systems

2. **Basic Implementation**
   - Run the starter assistant
   - Test with sample data
   - Customize prompts for Colppy

### Week 2: Integration
1. **Connect Real Data**
   - Integrate HubSpot API
   - Connect Mixpanel analytics
   - Test with actual business metrics

2. **Advanced Features**
   - Implement memory persistence
   - Add more specialized agents
   - Create automated workflows

### Week 3: Production
1. **Deploy Web Interface**
   - Launch Streamlit app
   - Configure for team access
   - Set up automated reports

2. **Scale and Optimize**
   - Monitor performance metrics
   - Gather user feedback
   - Iterate on capabilities

## 📚 Resources

### Technical Documentation
- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [HubSpot API Documentation](https://developers.hubspot.com/)
- [Mixpanel API Documentation](https://developer.mixpanel.com/)
- [Intercom Analytics & Export Toolkit](tools/docs/README_INTERCOM_CONSOLIDATED.md) - Complete guide for MCP and REST API integration

### Internal Documentation
- **[HubSpot Configuration](tools/docs/README_HUBSPOT_CONFIGURATION.md)** - Complete field mapping and API integration guide
- **[HubSpot Pagination Standards](tools/docs/README_HUBSPOT_PAGINATION_STANDARDS.md)** - Complete data retrieval methodology and best practices
- **[HubSpot Complete Retrieval Quick Reference](tools/docs/HUBSPOT_COMPLETE_RETRIEVAL_QUICK_REFERENCE.md)** - Ready-to-use scripts for complete data analysis
- **[HubSpot First Deal Won Date Implementation](tools/docs/HUBSPOT_FIRST_DEAL_WON_DATE_IMPLEMENTATION.md)** - Complete guide for tracking first deal won date at company level
- **[HubSpot Custom Code Testing Framework](tools/docs/README_HUBSPOT_CUSTOM_CODE_TESTING.md)** - Complete testing and validation system for HubSpot Custom Code workflows (✅ **CORRECTED DATE LOGIC VERIFIED**)
- **[Google Ads MCP](tools/docs/README_GOOGLE_ADS_MCP.md)** - Campaign performance analysis and optimization
- **[Meta Ads API](meta_ads_mcp_config/CAMPAIGN_STATUS_DETECTION_GUIDE.md)** - Campaign status detection and performance analysis

### Learning Materials
- **Agent Architecture**: NVIDIA's LLM Agent guides (linked in learning guide)
- **SaaS Metrics**: Key performance indicators for B2B SaaS
- **Product-Led Growth**: Strategies for PLG implementation

### Recommended Papers
1. "Generative Agents: Interactive Simulacra of Human Behavior"
2. "MRKL Systems: A modular, neuro-symbolic architecture"
3. "AutoGPT: An Autonomous GPT-4 Experiment"

## 🔒 Security & Privacy

- **API Keys**: Stored securely in environment variables
- **Data Privacy**: No customer data stored permanently
- **Access Control**: Configurable permissions for team usage
- **Audit Trail**: All interactions logged for compliance

## 🚀 Roadmap

### Phase 1 (Current)
- [x] Basic multi-agent architecture
- [x] HubSpot and Mixpanel integration
- [x] Web interface
- [x] Strategic planning capabilities

### Phase 2 (Next 30 days)
- [ ] Advanced memory system
- [ ] Automated report scheduling
- [ ] Team collaboration features
- [ ] Mobile-responsive interface

### Phase 3 (Next 90 days)
- [ ] Predictive analytics
- [ ] Advanced workflow automation
- [ ] Integration with more tools
- [ ] Multi-language support

## 🤝 Contributing

This is a personal CEO assistant project, but contributions and suggestions are welcome:

1. **Feedback**: Share your experience and suggestions
2. **Integrations**: Propose new tool integrations
3. **Features**: Suggest new agent capabilities
4. **Optimizations**: Performance and accuracy improvements

## 📞 Support

For questions or issues:
1. Check the `setup_instructions.md` for troubleshooting
2. Review the learning guide for implementation help
3. Consult the OpenAI Cookbook examples
4. Reach out for specific Colppy customizations

## 📄 License

This project is built on the OpenAI Cookbook foundation and follows the same open-source principles. Customize and adapt for your specific CEO needs.

---

**Built for accelerating SaaS B2B growth at Colppy.com** 🚀

*Remember: The goal is not just to build an AI assistant, but to create a strategic advantage that enhances your effectiveness as CEO and drives measurable business growth.*

## 🎯 Monthly PQL Analysis Tool

### Overview
Automated Product Qualified Lead (PQL) analysis with standardized metrics for consistent month-over-month tracking.

### Usage
```bash
# Current month-to-date analysis
./tools/scripts/run_monthly_pql.sh

# Specific month
./tools/scripts/run_monthly_pql.sh 2025-08

# Multi-month comparison
./tools/scripts/run_monthly_pql.sh last4

# Pre-configured comparison
./tools/scripts/run_monthly_pql.sh may-aug-2025
```

### Features
- **Standardized Metric**: PQL Rate = PQLs / All Contacts Created in Month
- **MoM Analysis**: Automatic calculation of deltas and trends
- **Multiple Formats**: JSON and CSV exports with timestamps
- **Real-time Data**: Direct HubSpot API integration using `activo` field
- **Executive Insights**: Key trends with visual indicators

### Output
- CSV/JSON files saved to `tools/outputs/`
- Console summary with MoM deltas and insights
- Standardized format for consistent reporting


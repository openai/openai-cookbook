# Funnel Analysis - Web Access Options

**Purpose**: Provide low-cost, straightforward ways for Head of Revenue to access and run funnel analysis scripts online.

**Last Updated**: 2025-12-24

---

## 🎯 Recommended Options (Ranked by Ease & Cost)

### 1. **Streamlit Web App** ⭐ **RECOMMENDED**
**Cost**: FREE (Streamlit Cloud free tier)  
**Setup Time**: 2-3 hours  
**Ease of Use**: ⭐⭐⭐⭐⭐ (Very Easy)

**Pros**:
- ✅ Free hosting on Streamlit Cloud
- ✅ Interactive UI - can run scripts directly from browser
- ✅ No frontend knowledge needed (pure Python)
- ✅ Built-in date pickers, file uploads, charts
- ✅ Share via URL (password-protected option)
- ✅ Auto-updates when code changes

**Cons**:
- ⚠️ Free tier: 1 app per account, public by default
- ⚠️ Requires GitHub repo connection

**Implementation**:
```python
# tools/scripts/hubspot/funnel_dashboard.py
import streamlit as st
import subprocess
import pandas as pd
from pathlib import Path

st.title("Colppy Funnel Analysis Dashboard")

# Date selection
col1, col2 = st.columns(2)
with col1:
    month = st.selectbox("Select Month", ["2025-12", "2025-11", "2025-10"])
with col2:
    funnel_type = st.radio("Funnel Type", ["Accountant", "SMB"])

# Run analysis button
if st.button("Run Analysis"):
    script = f"analyze_{funnel_type.lower()}_mql_funnel.py"
    result = subprocess.run(
        ["python", f"tools/scripts/hubspot/{script}", "--month", month],
        capture_output=True, text=True
    )
    st.code(result.stdout)
    
    # Load and display CSV
    csv_file = f"tools/outputs/{funnel_type.lower()}_mql_funnel_*.csv"
    if Path(csv_file).exists():
        df = pd.read_csv(csv_file)
        st.dataframe(df)
        st.download_button("Download CSV", df.to_csv(), "funnel_results.csv")
```

**Deployment**:
1. Push code to GitHub
2. Connect to Streamlit Cloud (free)
3. Share URL with Head of Revenue

**Cost**: $0/month

---

### 2. **Google Colab Notebook**
**Cost**: FREE  
**Setup Time**: 1 hour  
**Ease of Use**: ⭐⭐⭐⭐ (Easy)

**Pros**:
- ✅ Completely free
- ✅ No hosting needed
- ✅ Can run scripts directly
- ✅ Share via link (view-only or editable)
- ✅ Built-in charts and visualizations
- ✅ Can schedule runs (with Colab Pro - $10/month)

**Cons**:
- ⚠️ Requires Google account
- ⚠️ Session timeout after inactivity
- ⚠️ Less polished UI than Streamlit

**Implementation**:
```python
# Create: tools/notebooks/funnel_analysis.ipynb
# Install dependencies
!pip install pandas requests python-dotenv

# Run script
!python tools/scripts/hubspot/analyze_accountant_mql_funnel.py --month 2025-12

# Display results
import pandas as pd
df = pd.read_csv('tools/outputs/accountant_mql_funnel_20251201_20260101.csv')
df
```

**Deployment**:
1. Upload notebook to Google Colab
2. Share link with Head of Revenue
3. They can run cells directly

**Cost**: $0/month (or $10/month for Colab Pro with scheduled runs)

---

### 3. **Scheduled Email Reports** (Simplest)
**Cost**: FREE (if using existing email)  
**Setup Time**: 30 minutes  
**Ease of Use**: ⭐⭐⭐⭐⭐ (Very Easy)

**Pros**:
- ✅ Zero setup for user (just check email)
- ✅ Can schedule daily/weekly/monthly
- ✅ CSV attached, ready to open in Excel/Sheets
- ✅ No web interface needed

**Cons**:
- ⚠️ Not interactive (can't run on-demand)
- ⚠️ Requires email server setup

**Implementation**:
```python
# tools/scripts/hubspot/scheduled_funnel_report.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import subprocess
from datetime import datetime

# Run analysis
subprocess.run(["python", "analyze_accountant_mql_funnel.py", "--month", "2025-12"])

# Send email with CSV attachment
msg = MIMEMultipart()
msg['From'] = "reports@colppy.com"
msg['To'] = "head-of-revenue@colppy.com"
msg['Subject'] = f"Funnel Analysis - {datetime.now().strftime('%B %Y')}"

body = "Please find attached the funnel analysis report."
msg.attach(MIMEText(body, 'plain'))

# Attach CSV
with open("tools/outputs/accountant_mql_funnel_*.csv", "rb") as attachment:
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment', filename="funnel_report.csv")
    msg.attach(part)

# Send (configure SMTP)
server = smtplib.SMTP('smtp.gmail.com', 587)
server.starttls()
server.login("your-email", "your-password")
server.send_message(msg)
server.quit()
```

**Deployment**:
1. Set up cron job or GitHub Actions
2. Runs automatically, sends email
3. Head of Revenue receives CSV in inbox

**Cost**: $0/month (or email service cost if using SendGrid/Mailgun)

---

### 4. **GitHub Pages + Static HTML**
**Cost**: FREE  
**Setup Time**: 2 hours  
**Ease of Use**: ⭐⭐⭐ (Moderate)

**Pros**:
- ✅ Free hosting on GitHub Pages
- ✅ Can display results (read-only)
- ✅ Professional-looking
- ✅ No server needed

**Cons**:
- ⚠️ Read-only (can't run scripts)
- ⚠️ Requires manual CSV upload or automation
- ⚠️ Static (no interactivity)

**Implementation**:
- Generate HTML from CSV using existing `generate_visualization_report.py`
- Push HTML to GitHub Pages
- Auto-update via GitHub Actions

**Cost**: $0/month

---

### 5. **FastAPI + Simple HTML Frontend**
**Cost**: FREE (Render/Railway free tier) or $5-10/month  
**Setup Time**: 4-6 hours  
**Ease of Use**: ⭐⭐⭐ (Moderate)

**Pros**:
- ✅ Full control
- ✅ Can run scripts via API
- ✅ Customizable UI
- ✅ Can add authentication

**Cons**:
- ⚠️ More complex setup
- ⚠️ Requires backend knowledge
- ⚠️ Free tiers have limitations

**Cost**: $0-10/month

---

## 📊 Comparison Matrix

| Option | Cost | Setup Time | Ease of Use | Interactive | Best For |
|--------|------|------------|-------------|-------------|---------|
| **Streamlit** | $0 | 2-3 hrs | ⭐⭐⭐⭐⭐ | ✅ Yes | **Recommended** |
| **Google Colab** | $0 | 1 hr | ⭐⭐⭐⭐ | ✅ Yes | Quick setup |
| **Email Reports** | $0 | 30 min | ⭐⭐⭐⭐⭐ | ❌ No | Simplest |
| **GitHub Pages** | $0 | 2 hrs | ⭐⭐⭐ | ❌ No | Display only |
| **FastAPI** | $0-10 | 4-6 hrs | ⭐⭐⭐ | ✅ Yes | Full control |

---

## 🚀 Quick Start: Streamlit (Recommended)

### Step 1: Create Streamlit App
```bash
# Create new file
touch tools/scripts/hubspot/funnel_dashboard.py
```

### Step 2: Install Streamlit
```bash
pip install streamlit plotly pandas
```

### Step 3: Run Locally
```bash
streamlit run tools/scripts/hubspot/funnel_dashboard.py
```

### Step 4: Deploy to Streamlit Cloud
1. Push code to GitHub
2. Go to share.streamlit.io
3. Connect GitHub repo
4. Deploy (free)

### Step 5: Share URL
- Share the Streamlit Cloud URL with Head of Revenue
- They can access from any browser
- No installation needed

---

## 💡 Recommendation

**For Colppy's use case, I recommend:**

1. **Primary**: **Streamlit Web App** - Best balance of ease, cost, and functionality
2. **Backup**: **Scheduled Email Reports** - For automated weekly/monthly delivery

**Why Streamlit?**
- Head of Revenue can run analysis on-demand
- Interactive date selection
- Visual charts and tables
- Download CSV directly
- Free hosting
- Professional appearance
- No technical knowledge needed to use

**Implementation Priority:**
1. ✅ Create Streamlit dashboard (2-3 hours)
2. ✅ Deploy to Streamlit Cloud (30 minutes)
3. ✅ Set up scheduled email backup (optional, 30 minutes)

---

## 📝 Next Steps

Would you like me to:
1. Create the Streamlit dashboard app?
2. Set up the email automation script?
3. Create a Google Colab notebook template?

Let me know which option you prefer and I'll implement it!








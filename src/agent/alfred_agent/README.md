# 🦇 Alfred: The Wayne Household Assistant

Welcome to the team. You are now a part of the Alfred project—a specialized AI agent designed to manage both professional duties and "Special Gotham Projects" (Special Ops/Superhero tasks) for Master Bruce.

This guide will take you from a fresh computer to a fully running Alfred Agent.

---

## 🛠️ Step 1: The Utility Belt (Software Setup)

If you have nothing installed, follow these steps in order:

1. **Install Python**: [Download Python 3.12](https://www.python.org/downloads/windows/). During installation, **make sure to check the box that says "Add Python to PATH."**
2. **Install Git**: [Download Git for Windows](https://git-scm.com/download/win).
3. **Install Google Cloud (gcloud)**: [Follow these instructions](https://cloud.google.com/sdk/docs/install#windows).

---

## 🏗️ Step 2: Getting the Code (Clone & Open)

Open your terminal (PowerShell or Command Prompt) and run these commands one at a time:

1. **Clone the project**

   ```powershell
   git clone https://github.com/manugerahgunawan/alfred.git
   ```

2. **Move into the folder**

   ```powershell
   cd alfred/src/agent/alfred_agent
   ```

---

## ⚙️ Step 3: Installing Antigravity (The ADK)

Alfred runs on the **Antigravity (ADK)** framework. To install it and all other requirements:

1. **Create a virtual environment** (optional but recommended)

   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

2. **Install the toolkit**

   ```powershell
   pip install google-adk
   pip install -r requirements.txt
   ```

---

## 🔑 Step 4: The Secret Keys (.env)

Alfred needs a few "Secret Keys" to function. In this folder, you will find a file named `.env`. If it doesn't exist, create it and paste the following:

```env
MODEL=gemini-2.5-flash
PROJECT_ID=alfred-492407
LOCATION=us-central1
MCP_URL=https://workspace-mcp-181562945855.asia-southeast2.run.app/mcp
GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\your\credentials.json
GOOGLE_ACCESS_TOKEN=your_temp_token_here
```

### ⚡ How to get your Access Token

The `GOOGLE_ACCESS_TOKEN` expires every hour. To refresh it, open your terminal (Command Prompt or PowerShell) and run:

```powershell
gcloud auth print-access-token
```

Copy that code and paste it back into your `.env` file.

---

## 🚀 Step 5: Launching Alfred

1. **Open your terminal** in this folder (`c:\Users\manug\Documents\Alfred\alfred\src\agent\alfred_agent`).
2. **Run Alfred**
   ```powershell
   adk web .
   ```
3. **Open your browser**: Go to the URL shown in the terminal (usually `http://localhost:8080`).

---

## 🦸‍♂️ Step 6: Hero Training (Expanding Alfred)

Want to give Alfred new powers? All the "brains" are located in **`agent.py`**.

### Change How He Speaks (Persona)

Look for any `Agent(` definition in `agent.py` and modify the `instruction` property.
*Example: If you want him to be even more sarcastic, add it to his instruction.*

### Add New Tools (Technological Upgrades)

Alfred uses **MCP (Model Context Protocol)** to talk to the world (Gmail, Calendar, etc.).

- Look for `workspace_toolset`.
- You can add or remove tools by changing the `tools=[...]` list inside any agent definition.

### Create a New Specialist (Sub-Agents)

If we need a "Batmobile Repair Specialist" agent:

1. Define a new `Agent` in `agent.py`.
2. Add it to the `sub_agents` list in `alfred_core_workflow`.

---

## 🛡️ Final Note

*"Be present at work. Be present at home. I shall handle the rest."*

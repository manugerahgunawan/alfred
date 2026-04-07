# Alfred Agent — Local Setup Guide (Windows)

> Everything you need to run the agent on your local machine using PowerShell.
> All commands are run from this folder: `src/agent/alfred_agent/`

---

## Part 1 — Prerequisites

### Step 1: Install Python (if not already installed)

Check if Python is installed:
```powershell
python --version
```

If not installed, download Python 3.11+ from:
👉 https://www.python.org/downloads/

During install, **tick the box** that says "Add python.exe to PATH".

---

### Step 2: Install Google Cloud SDK (`gcloud`)

`gcloud` is needed to authenticate your machine with Google Cloud (Vertex AI, Cloud Logging).

1. Download the installer from:
   👉 https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe

2. Run the installer. Accept defaults.

3. After install, **open a new PowerShell window** and verify:
   ```powershell
   gcloud --version
   ```

---

## Part 2 — Authenticate with Google Cloud

All of the following steps are run in PowerShell from this folder:
`c:\Users\manug\Documents\Alfred\alfred\src\agent\alfred_agent\`

### Step 3: Log into your Google account

```powershell
gcloud auth login
```
A browser window will open. Sign in with your Google account.

---

### Step 4: Set your GCP project

```powershell
gcloud config set project alfred-492407
```

---

### Step 5: Set up Application Default Credentials (ADC)

This is what the agent uses behind the scenes to call Vertex AI and Cloud Logging. Run:
```powershell
gcloud auth application-default login
```
A browser window will open again. Sign in with the **same Google account**.

> **Why twice?** Step 3 logs *you* in. Step 5 creates a credential file your Python code reads automatically. They are separate.

---

## Part 3 — Set Up a Python Virtual Environment

Do this **inside the `alfred_agent` folder**. A virtual environment keeps this project's packages isolated from your other Python projects.

### Step 6: Create the virtual environment

```powershell
python -m venv venv
```

This creates a `venv/` folder inside `alfred_agent/`.

---

### Step 7: Activate the virtual environment

```powershell
.\venv\Scripts\Activate.ps1
```

Your prompt will change to show `(venv)` at the start. You should see this:
```
(venv) PS c:\...\alfred_agent>
```

> **If you get a script execution error**, run this first, then retry Step 7:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

---

### Step 8: Install the dependencies

```powershell
pip install -r requirements.txt
```

This installs `google-adk`, `langchain-community`, and `wikipedia`.

---

## Part 4 — Configure Environment Variables

### Step 9: Check the `.env` file

The `.env` file lives in the **project root** (`alfred/`), not in this folder. The agent loads it automatically using `load_dotenv()`. It should already contain:

```
MODEL=gemini-2.0-flash
GOOGLE_ACCESS_TOKEN=...
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
```

No changes needed — it is already set up.

---

## Part 5 — Run the Agent

### Step 10: Use the ADK Web UI (Recommended for testing)

`google-adk` comes with a built-in web interface for chatting with your agent. From inside `alfred_agent/`:

```powershell
adk web
```

Then open your browser to: http://localhost:8000

You will see the Alfred agent in the UI. Type a message to start.


---

### Step 11 (Alternative): Run the ADK CLI

If you prefer the terminal:

```powershell
adk run alfred_agent
```

> Note: `adk run` expects a **folder name that matches the agent module**. Since you are already inside `alfred_agent/`, run this from the **parent folder** instead:
> ```powershell
> # Go up one level first:
> cd ..
> adk run alfred_agent
> ```

---

## Part 6 — Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `gcloud is not recognized` | Google Cloud SDK not installed | Complete Step 2 |
| `google.auth.exceptions.DefaultCredentialsError` | ADC not set up | Complete Step 5 |
| `PermissionDenied: Vertex AI` | Wrong project or project not enabled | Run Step 4, then enable Vertex AI in the GCP Console |
| `ModuleNotFoundError: google.adk` | Dependencies not installed | Run Step 8, and make sure `(venv)` is active |
| `venv\Scripts\Activate.ps1 cannot be loaded` | PowerShell execution policy blocked scripts | Run the `Set-ExecutionPolicy` command from Step 7 |
| `(venv)` not showing | Virtual env not activated | Re-run Step 7 every time you open a new terminal |

---

## Quick Reference — Commands in Order

```powershell
# One-time setup (do once per machine)
gcloud auth login
gcloud config set project alfred-492407
gcloud auth application-default login

# Every time you open a new terminal in alfred_agent/
.\venv\Scripts\Activate.ps1

# One-time dependency install
pip install -r requirements.txt

# Run the agent
adk web
```

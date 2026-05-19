# Nexus Render Hybrid

A Manus-style AI agent dashboard designed for Render Free Tier with a private Mac Ollama fallback.

## Features
- **AI Routing:** Automatically falls back from Mac Connector to Gemini, Groq, OpenRouter, and more.
- **Mobile-First:** Polished UI designed for iPhone control.
- **Live Logs:** Real-time system diagnostics directly in the browser.
- **Skills & Connectors:** Dynamic system prompt injection based on toggled skills.

## Cloud Deployment (Render)
1. Create a new Web Service on Render.
2. Connect this repository.
3. Set the Environment Variables as listed in `.env.example`.
4. Deploy.

## Mac Connector Setup (Local)
To use your local Ollama vault:
1. Install Ollama and pull a model (e.g., `llama3.2` or `llama3`).
2. Run the connector:
   ```bash
   cd connector
   export MAC_CONNECTOR_SECRET="your-secret"
   export OLLAMA_MODEL="llama3.2" # or llama3
   python3 -m uvicorn mac_control:APP --host 0.0.0.0 --port 8800
   ```
3. Use a tool like `ngrok` or `cloudflared` to expose port 8800.
4. Set the resulting URL as `MAC_CONNECTOR_URL` in your Render environment variables.

## Usage
- Access your app at `https://your-app.onrender.com`.
- Use the **Logs** tab to verify provider connections.
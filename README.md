---
title: AidFidelis Symptom Checker API
emoji: 🩺
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
---

# Symptom Disease Model

This project classifies symptom descriptions into likely disease labels using a transformer-based text classification model.

## Structure

- `original-model/`: the pretrained model checkpoint used for inference
- `symptom_disease_model/`: reusable Python package for inference
- `tests/`: regression tests for the inference pipeline
- `training/`: dataset inspection utilities
- `train.py`: training entry point for fine-tuning the model

## Quick start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run inference:
   ```bash
   python -c "from symptom_disease_model.inference import DiseaseClassifier; c = DiseaseClassifier(); print(c.predict('I have fever, headache, and body pains.'))"
   ```

3. Run tests:
   ```bash
   python -m unittest tests.test_inference
   ```

## Deploy the API

### Host the model on your own PC

The backend can run on your PC while the frontend is deployed elsewhere.
From PowerShell, run:

```powershell
Set-Location "C:\path\to\symptom-disease-model"
python -m pip install -r requirements.txt
.\run_backend.ps1
```

If PowerShell blocks the script, run the command directly:

```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Verify locally at `http://127.0.0.1:8000/health`. Devices on the same Wi-Fi
can use `http://YOUR_PC_LAN_IP:8000`, but a deployed frontend cannot call your
PC's `localhost` or private LAN address.

For a fast presentation or classifier-only test, add these settings to `.env`:

```text
ENABLE_GEMINI_EXPLANATION=false
ENABLE_MEDICATION_RULES=false
```

This returns the DistilBERT predictions and safety guidance without waiting
for Groq or Firestore. Set both values back to `true` for the full workflow.

Groq retries default to one attempt per model so the streaming endpoint does
not exceed a frontend timeout. Increase `GROQ_MAX_ATTEMPTS` only when you want
slower retries for temporary provider failures.

`GROQ_MODELS` controls the fallback list. The default uses
`llama-3.3-70b-versatile` and lets the application return its local fallback
quickly when Groq is unavailable.

For a deployed frontend, expose the local API through an HTTPS tunnel. For
example, with Cloudflare Tunnel:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Or with ngrok:

```powershell
ngrok http 8000
```

Put the generated HTTPS origin in your local `.env`:

```text
CORS_ORIGINS=https://your-frontend.example.com
```

Then configure the frontend's API base URL to the generated HTTPS tunnel URL,
for example `https://random-name.trycloudflare.com`. Keep the terminal and
the tunnel running while users need the AI feature.

### Cloud deployment

The frontend cannot call the Python model directly. Deploy this backend as a
separate web service, then set the frontend API base URL to the backend URL.

This repository includes `render.yaml` for Render. In the Render dashboard,
create a Blueprint from the repository and add these secret/environment values:

- `GROQ_API_KEY`: your Groq API key
- `FIREBASE_SERVICE_ACCOUNT_JSON`: the complete Firebase Admin service-account
   JSON object on one line
- `CORS_ORIGINS`: the deployed frontend origin, for example
   `https://your-frontend.example.com`

The backend start command is:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

After deployment, verify:

```text
https://your-backend.example.com/health
```

The frontend should call:

```text
POST https://your-backend.example.com/api/symptom-check
POST https://your-backend.example.com/api/symptom-check/stream
```

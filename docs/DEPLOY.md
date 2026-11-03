# Hosting a demo

The repo has a `Dockerfile` that builds the frontend and serves it from the FastAPI backend,
exactly like `npm run build` + `uvicorn app.main:app` on the laptop. The assistant uses Groq;
there is no Ollama in the cloud, so document search is keyword-only (`EMBEDDINGS=off`).

**Secrets are never in the repo or the image.** You pass two values when you deploy:

| Variable | What it is |
|---|---|
| `GROQ_API_KEY` | Your key from console.groq.com/keys |
| `APP_SECRET` | Any long random string; it signs the login cookies |

**Two ways on GCP.** Option 1 is the app alone with Groq: cheap and simplest. Option 1b adds
Ollama on a GPU next to it. They are separate services, so you can run either or both.

**Data.** The database is SQLite inside the container. The image already holds the venues,
users, committed timetables, circulars and reports; each start adds the demo bookings (dated
relative to today). Anything you change during the demo is kept while the container runs, and
a restart or redeploy goes back to fresh demo data. That's why Cloud Run is set to exactly one
instance below: two instances would each have their own database.

**Time zone.** The image runs in `Asia/Kolkata`, because the app uses local time for "today".

## Option 1: Google Cloud Run (recommended, uses your GCP credits)

Always on for the demo, HTTPS, about 15 seconds to start, and costs roughly a dollar or two a
day with one instance kept warm. Everything below runs in **Cloud Shell**, so nothing needs to be
installed on the laptop.

1. Open https://console.cloud.google.com, pick (or create) the project that has your credits,
   and click the **Activate Cloud Shell** button (`>_`, top right).
2. In Cloud Shell, paste these one block at a time:

   ```bash
   gcloud config set project YOUR_PROJECT_ID
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

   git clone https://github.com/waltervetrivel/agentic_venue_booker.git
   cd agentic_venue_booker
   ```

   ```bash
   # Paste your Groq key when asked and press Enter (it isn't shown or saved in a file).
   read -s -p "Groq API key: " GROQ_KEY; echo
   ```

   ```bash
   gcloud run deploy venue-booker \
     --source . \
     --region asia-south1 \
     --allow-unauthenticated \
     --memory 1Gi --cpu 1 \
     --min-instances 1 --max-instances 1 \
     --set-env-vars "GROQ_API_KEY=$GROQ_KEY,APP_SECRET=$(openssl rand -hex 32)"
   ```

   Say **Y** if it asks to create an Artifact Registry repository. The build takes about
   5 minutes and ends with a `Service URL: https://venue-booker-....run.app`. Open it.
3. Optional: make links in student emails point at the hosted app.

   ```bash
   URL=$(gcloud run services describe venue-booker --region asia-south1 --format 'value(status.url)')
   gcloud run services update venue-booker --region asia-south1 --update-env-vars PUBLIC_URL=$URL
   ```

**Check before the demo:** log in as the Director, open **Settings**: the Groq key should show
as set (from the environment). Ask the assistant "Is CC5 free tomorrow from 10 to 12?".

**Reset to fresh demo data:** `gcloud run services update venue-booker --region asia-south1
--update-env-vars RESET=$(date +%s)` starts a new container.

**Change the Groq key:** `gcloud run services update venue-booker --region asia-south1
--update-env-vars GROQ_API_KEY=new-key` (or set it in **Settings** as the Director; that copy
is lost on the next restart).

**After the demo, delete it** so it stops using credits:

```bash
gcloud run services delete venue-booker --region asia-south1
gcloud artifacts repositories delete cloud-run-source-deploy --location asia-south1
```

The env var is visible to people with access to your GCP project, which is fine for a demo.
For longer use, put the key in Secret Manager and use `--set-secrets GROQ_API_KEY=groq-key:latest`.

## Option 1b: Cloud Run with a GPU and Ollama (optional)

Same app, plus Ollama on an NVIDIA L4 GPU in the same Cloud Run instance, so the assistant can
run a local model (`qwen3.5:9b` by default, much faster than on a laptop) and document search
matches by meaning again. Groq stays available: people switch in the chat panel's model menu.

- **Region:** the L4 is generally available in Singapore (`asia-southeast1`); Mumbai is
  invitation-only.
- **Cost:** a GPU instance is at least 8 CPUs and 32 GB with the GPU, roughly **$1.50–2 an hour**
  while it runs (it's billed even when idle). Deploy it on the day and delete it afterwards.
- **Billing:** the project needs billing enabled; free-trial credits may not allow GPUs. If the
  deploy fails with a GPU quota or billing error, use Option 1 (Groq only).
- **Data:** like Option 1, one instance with its own SQLite database, reset on restart.

The app talks to Ollama on `localhost:11434` inside the instance. Only the app's port is public,
so nobody else can use the GPU. The models are baked into the Ollama image (about 8 GB), so the
first deploy takes 15–25 minutes; do it at least an hour before the demo.

In Cloud Shell, after `cd agentic_venue_booker` (see Option 1):

```bash
REGION=asia-southeast1
REPO=$REGION-docker.pkg.dev/$(gcloud config get-value project)/venue-booker
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories create venue-booker --repository-format docker --location $REGION

# Build both images (the Ollama one downloads the models; allow ~15 minutes).
gcloud builds submit --tag $REPO/app .
gcloud builds submit deploy/ollama --tag $REPO/ollama --machine-type e2-highcpu-8 --timeout 45m
```

```bash
# Fill in the service file and deploy. DEFAULT_PROVIDER=ollama makes the local model the
# default instead of Groq.
export REGION APP_IMAGE=$REPO/app OLLAMA_IMAGE=$REPO/ollama CHAT_MODEL=qwen3.5:9b DEFAULT_PROVIDER=groq
read -s -p "Groq API key: " GROQ_KEY; echo; export GROQ_KEY
export APP_SECRET=$(openssl rand -hex 32)
envsubst < deploy/cloudrun-gpu.yaml > /tmp/service.yaml
gcloud run services replace /tmp/service.yaml --region $REGION; rm /tmp/service.yaml

# Let anyone with the link open it.
gcloud run services add-iam-policy-binding venue-booker-gpu --region $REGION \
  --member allUsers --role roles/run.invoker
gcloud run services describe venue-booker-gpu --region $REGION --format 'value(status.url)'
```

**Check before the demo:** in the chat panel's model menu, pick Ollama and ask "Is CC5 free
tomorrow from 10 to 12?". The app's logs (Cloud Run → venue-booker-gpu → Logs) should show
`276 of 276 documents are indexed by meaning` and `Loaded qwen3.5:9b in Ollama`.

**A different model:** change `CHAT_MODEL` in `deploy/ollama/Dockerfile`, rebuild the Ollama
image, and deploy again with the same `CHAT_MODEL`. `qwen3.5:4b` is faster; `qwen3.5:27b` (17 GB) is smarter but leaves
little GPU memory to spare.

**After the demo, delete it:**

```bash
gcloud run services delete venue-booker-gpu --region asia-southeast1
gcloud artifacts repositories delete venue-booker --location asia-southeast1
```

## Option 2: Render (free, no card; backup)

Free web services sleep after 15 minutes without visitors. The first visit after that takes
about a minute, and sleeping resets the data. Open the URL a few minutes before the demo.

1. Sign in at https://render.com with GitHub and click **New → Web Service**.
2. Pick the `agentic_venue_booker` repository. Render sees the `Dockerfile`; choose
   **Free**.
3. Under **Environment Variables** add `GROQ_API_KEY` (your key) and `APP_SECRET` (any long
   random string), then **Deploy**. The URL is `https://<name>.onrender.com`.

## A note on access

Anyone with the URL can open the app, and the demo accounts all use the password `password`.
That's fine for a day, but share the link only with the audience, keep an eye on your Groq
usage, and delete the service afterwards.

## Try the image locally

```bash
docker build -t venue-booker .
docker run --rm -p 8080:8080 -e APP_SECRET=dev -e GROQ_API_KEY=your-key -e COOKIE_SECURE=false venue-booker
```

`COOKIE_SECURE=false` is only for plain `http://localhost`; the hosted HTTPS sites keep the
default (`true`).

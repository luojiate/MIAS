# MIAS backend

FastAPI service for the Medimage Analysis System. Stores users and analyses in MongoDB (`mias` database, `users` and `analyses` collections).

## Setup

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

MongoDB must be running at `mongodb://127.0.0.1:27017`.

## Run

```bash
cd backend
source .venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

API: `http://localhost:8000`  
Uploaded files: `http://localhost:8000/uploads/<filename>`

## Image analysis hook

`POST /upload-image` runs `vision/main.py <image-path>` and expects JSON on stdout (`outerFat`, `innerFat`, `length`, `width`). Replace that script with a real model. If analysis fails, the upload still succeeds with placeholder metrics (zeros).

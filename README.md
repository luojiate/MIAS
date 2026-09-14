# Medimage Analysis System (MIAS)

Web app for uploading medical images, storing fat/length measurements, and reviewing your personal analyses. This repo is a Vite + React 19 frontend and a FastAPI + MongoDB backend that replace the older Create React App / Express stack.

## Stack

- **Frontend:** Vite, React 19, TypeScript, React Router, Tailwind CSS v4, axios, react-hook-form
- **Backend:** FastAPI, Motor (async MongoDB), cookie sessions, bcrypt password hashes
- **Database:** MongoDB at `mongodb://127.0.0.1:27017`, database name `mias`

## 1. MongoDB

The API expects MongoDB on localhost port **27017**.

**Windows (service):** install [MongoDB Community Server](https://www.mongodb.com/try/download/community) and keep the MongoDB service running (Services → MongoDB).

**macOS:** `brew services start mongodb-community`

**Linux:** install MongoDB and start `mongod`, or run:

```bash
mongod --dbpath /data/db --bind_ip 127.0.0.1 --port 27017
```

## 2. Backend (`http://localhost:8000`)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

CORS allows `http://localhost:5173` and `http://localhost:3000` with credentials. Cookie sessions require the browser to send cookies (`credentials: 'include'`).

## 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

- `VITE_BACKEND_URL=http://localhost:8000` talks to FastAPI directly (matches `.env.example`).
- An empty `VITE_BACKEND_URL` uses the Vite dev-server proxy to port 8000 (same-origin cookies). The checked-in `frontend/.env` uses the proxy so local Preview works.

Open the URL printed by Vite (this project’s dev server defaults to port **43173**).

```bash
npm run build     # production build
npm run preview   # serve the build
```

## API (cookie session)

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/login` | no | `{ email, password }` → `{ message, user }` (`user.ID`, `name`, `email`) |
| POST | `/logout` | no | Clears the session cookie |
| POST | `/register` | no | `{ name, email, password }` — **400** if email exists |
| POST | `/upload-image` | yes | multipart field `image` → `{ image, outerFat, innerFat, length, width }` |
| POST | `/create` | yes | `{ number, description, userid }` plus optional `image` |
| GET | `/personal` | yes | Analyses for the signed-in user |
| DELETE | `/delete/{id}` | yes | Only the owner can delete |

On **401**, the frontend redirects to `/login`.

## Layout

```
frontend/   Vite React 19 TypeScript app
backend/    FastAPI app (`app.py`), uploads/, vision/main.py
```

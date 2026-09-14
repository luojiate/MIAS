# MIAS frontend

Vite + React 19 + TypeScript UI for the Medimage Analysis System.

## Run

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The dev server (port `43173`) proxies API calls to `http://127.0.0.1:8000`. To call the backend directly, set:

```
VITE_BACKEND_URL=http://localhost:8000
```

Requests use `withCredentials: true` so the FastAPI session cookie is sent.

## Scripts

- `npm run dev` — development server
- `npm run build` — production build
- `npm run preview` — preview the production build

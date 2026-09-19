# Medimage Analysis System (MIAS)

上傳醫學影像、以 ONNX 分割內／外層脂肪、儲存量測結果，並在個人頁回顧分析紀錄。
前端為 Vite + React 19；後端為 FastAPI + MongoDB；推論為 EfficientTransUNet（ONNX Runtime）。

Repo：https://github.com/luojiate/MIAS

## 技術棧

| 層級 | 技術 |
| --- | --- |
| Frontend | Vite、React 19、TypeScript、React Router、Tailwind CSS v4、axios、react-hook-form |
| Frontend 工具 | **fnm**（Node 24）+ **pnpm** |
| Backend | FastAPI、Motor（async MongoDB）、cookie session、bcrypt |
| Backend 工具 | **uv**（`pyproject.toml` / `uv.lock`） |
| Database | 本機 MongoDB `mongodb://127.0.0.1:27017`，資料庫名 `mias`；雲端用 **MongoDB Atlas** |
| 推論 | ONNX Runtime：`efficientTransUnetB3_inner.onnx` + `efficientTransUnetB0_outer.onnx` |
| 公開部署 | **Render** Docker 單一服務（FastAPI 同時提供 API + 靜態前端）+ Atlas。Vercel 前端為可選。 |

## 快速啟動（Windows）

前置：MongoDB 服務、[uv](https://docs.astral.sh/uv/)、[fnm](https://github.com/Schniz/fnm)、pnpm（建議 `corepack enable`）。

```bat
cd mias-origin
start-local.bat
```

- Frontend：http://127.0.0.1:5173
- Backend：http://127.0.0.1:8000

`start-local.bat` 會嘗試啟動 MongoDB 服務，並用 `uv run uvicorn` 與 `fnm exec -- pnpm run dev` 開後端／前端。

## 1. MongoDB

API 需要本機 **27017**。

**Windows：** 安裝 [MongoDB Community Server](https://www.mongodb.com/try/download/community)，保持 MongoDB 服務執行中。

**macOS：** `brew services start mongodb-community`

**Linux：** 啟動 `mongod`，或：

```bash
mongod --dbpath /data/db --bind_ip 127.0.0.1 --port 27017
```

## 2. Backend（uv）

```bash
cd backend
uv sync
cp .env.example .env   # Windows: copy .env.example .env
uv run uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

- 依賴以 `pyproject.toml` / `uv.lock` 為準；`requirements.txt` 由 `uv export` 產生。
- 預設不含 PyTorch（線上推論走 ONNX）。若要訓練相關套件：`uv sync --extra train`。
- ONNX 權重預設路徑：`backend/models/`
  - `efficientTransUnetB3_inner.onnx`
  - `efficientTransUnetB0_outer.onnx`
- 執行裝置可用環境變數 `MIAS_ORT_PROVIDERS`（預設 `CPUExecutionProvider`；GPU 需對應 CUDA／cuDNN）。

CORS 允許 `http://localhost:5173` 與 `http://localhost:3000`（含 credentials）。

### 推論前處理（對齊舊專案）

上傳影像後的管線與舊版 web `Crop_and_CLAHE` 一致：

1. 灰階讀圖（OpenCV）
2. 左側約 12 px 尺規條 + 中心裁切 **560×560**
3. CLAHE（`clipLimit=2.0`，`tileGridSize=(8,8)`）
4. 縮放至 **256×256**，除以 255，NCHW `(1,1,256,256)`
5. 內／外層分別推論 → 機率圖縮回 560 → 門檻化
6. 外層 `Max_Area`；內層去掉小連通區域（`min_area=60`）
7. 疊圖畫在 CLAHE 後的 CT 裁切上（外層琥珀、內層青）

量測（尺規成功時）：

- `outerFat` / `innerFat`：**cm²**
- `length` / `width`：**cm**

尺規失敗時上述數值為 `0.0`，疊圖仍會產出。實作見 `backend/vision/preprocess.py`、`backend/vision/infer.py`。

測試：

```bash
cd backend
uv run python -m unittest tests.test_preprocess tests.test_batch_upload tests.test_deploy_files -v
```

`tests.test_batch_upload` 需要 `httpx`（FastAPI TestClient）。若尚未安裝：`uv run --with httpx python -m unittest tests.test_batch_upload -v`。

## 3. Frontend（fnm + pnpm）

```bash
cd frontend
fnm use          # 讀取 .node-version → Node 24
pnpm install
cp .env.example .env   # Windows: copy .env.example .env
pnpm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

- `VITE_BACKEND_URL=http://localhost:8000` 直接打 FastAPI。
- 空的 `VITE_BACKEND_URL` 走 Vite proxy 到 8000（同網域 cookie）。

```bash
pnpm run build
pnpm run preview
```

新增分析頁可一次選擇多張影像（最多 8 張、每張 10 MB），佇列顯示等待中／分析中／完成／失敗；個人頁可回看疊圖與量測。

## API（cookie session）

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/login` | no | `{ email, password }` → `{ message, user }` |
| POST | `/logout` | no | 清除 session cookie |
| POST | `/register` | no | `{ name, email, password }`；email 重複 → 400 |
| POST | `/upload-image` | yes | multipart `image` → 量測 + 疊圖 URL（`overlay` 等） |
| POST | `/upload-images` | yes | multipart `images`（最多 8 張）→ `{ results, succeeded, failed }`；伺服器依序推論 |
| POST | `/create` | yes | 儲存單筆分析（含影像／疊圖資訊） |
| POST | `/create-batch` | yes | `{ items: [...] }` 一次寫入多筆個人紀錄 |
| GET | `/personal` | yes | 目前使用者的分析列表 |
| DELETE | `/delete/{id}` | yes | 僅擁有者可刪 |

批次上限與錯誤訊息為繁體中文（空清單、超過 8 張、空檔、非 JPG/PNG/GIF、超過 10 MB）。

401 時前端導向 `/login`。

## 目錄結構

```
frontend/          Vite React 19 + TypeScript（pnpm）
backend/           FastAPI（uv）
  app.py
  analyzer.py      呼叫 vision.infer
  vision/          ONNX 推論、Crop_and_CLAHE、疊圖
  models/          *.onnx 權重
  tests/           前處理／推論單元測試
Dockerfile         多階段：pnpm build → CPU onnxruntime → 同源 SPA
render.yaml        Render Blueprint（單一 web service）
start-local.bat    Windows 一鍵啟動
```

## 環境變數（常用）

見 `backend/.env.example`：

- `MONGO_URI` / `MONGO_DB` / `SESSION_SECRET` / `PUBLIC_URL`
- `CORS_ORIGINS`（可選；同源部署請留空）
- `SESSION_SAMESITE` / `SESSION_HTTPS_ONLY`
- `MIAS_INNER_ONNX` / `MIAS_OUTER_ONNX`
- `MIAS_INFER_SIZE`（預設 256）
- `MIAS_MASK_THRESH`（預設 0.5）
- `MIAS_ORT_PROVIDERS`

## Deploy（公開雲端，104 履歷連結）

預設路徑：**一個 Render Web Service**（Docker 映像同時跑 FastAPI API 與前端 `dist`）+ **MongoDB Atlas**。履歷上只放這一個 HTTPS URL，不必讓自己的電腦開機。本機仍用 uv + fnm/pnpm。

### 1. MongoDB Atlas

1. 建立免費叢集，資料庫名建議 `mias`。
2. Database Access 新增使用者，記下密碼。
3. Network Access 加入 `0.0.0.0/0`（讓 Render 出站 IP 連得上；此為 demo 便利設定）。
4. 複製連線字串 `MONGO_URI`（形如 `mongodb+srv://user:pass@cluster.../?retryWrites=true&w=majority`）。

### 2. 連接 GitHub → Render

1. 將此 repo 推上 GitHub（已公開即可）。
2. [Render](https://render.com) → **New** → **Blueprint**，選 repo 根目錄的 `render.yaml`；或 **New Web Service** → Docker，Dockerfile 路徑為 repo 根目錄 `Dockerfile`。
3. 免費方案會在閒置後休眠，**第一次開啟可能要等 30–90 秒**（cold start）。推論在 CPU 上跑，不需要 GPU。

建置過程：Node 24 + pnpm 編譯前端（`VITE_BACKEND_URL` 為空＝同源）→ Python 3.12 安裝 **CPU `onnxruntime`**（覆寫本機的 `onnxruntime-gpu`）→ 複製 `backend/models/*.onnx`。

### 3. 環境變數

| 變數 | 說明 |
| --- | --- |
| `MONGO_URI` | Atlas 連線字串（必填，勿提交進 git） |
| `MONGO_DB` | 預設 `mias` |
| `SESSION_SECRET` | 隨機字串（Blueprint 可自動產生） |
| `PUBLIC_URL` | 部署後的 Render URL，例如 `https://mias.onrender.com`（未填時會嘗試 `RENDER_EXTERNAL_URL`） |
| `CORS_ORIGINS` | **同源部署請留空**。僅在另開 Vercel 前端時填 `https://xxx.vercel.app` |
| `MIAS_ORT_PROVIDERS` | `CPUExecutionProvider` |
| `SESSION_SAMESITE` | 同源預設 `lax` |

上傳目錄 `/app/uploads` 可寫入，但 **免費方案磁碟是 ephemeral**：實例休眠／重部署後檔案會消失，僅適合 demo。

### 4. 履歷連結

部署完成後打開 `https://<服務名>.onrender.com`，註冊一個 **demo 帳號**、走一遍上傳與個人頁。這個 URL 就是 104 上放的連結。

### 5. Cookie／CORS（同源 vs 分站）

- **建議（本設定的預設）：** 瀏覽器只打 Render 同一個 origin。Session cookie 用 `SameSite=Lax`；HTTPS 時帶 `Secure`。前端 build 的 `VITE_BACKEND_URL` 為空，axios 走相對路徑。
- **可選：Vercel 前端 + Render API。** SPA 在 `*.vercel.app`、API 在 `*.onrender.com` 時，跨站 cookie 常被擋。必須同時：
  1. FastAPI：`SESSION_SAMESITE=none`、`SESSION_HTTPS_ONLY=true`（`SameSite=None; Secure`）
  2. `CORS_ORIGINS=https://your-app.vercel.app`（明確 origin，且 `allow_credentials=True`）
  3. 前端 `VITE_BACKEND_URL=https://your-service.onrender.com`、`withCredentials: true`
  4. 若仍失敗，改回「單一 Render URL」，不要用 Vercel。

可選 Vercel：在 `frontend/` 用 pnpm build，Root Directory 設 `frontend`，環境變數 `VITE_BACKEND_URL` 指向 Render。104 請仍優先用 Render 單一 URL。

### 6. 隱私與醫療資料

- 使用 **demo 帳號與樣本影像**，不要上傳可識別病人的真實資料。
- 免費 MongoDB / Render 不是 HIPAA／醫院等級環境；本專案僅供研究與作品展示。
- 請遵守機構 IRB 與資料使用規範。

本機驗證映像（需已安裝 Docker 與可連的 MongoDB）：

```bash
docker build -t mias .
docker run --rm -p 8000:8000 \
  -e PORT=8000 \
  -e MONGO_URI="mongodb://host.docker.internal:27017" \
  -e MONGO_DB=mias \
  -e SESSION_SECRET=dev \
  -e PUBLIC_URL=http://localhost:8000 \
  mias
```

## License / 備註

本專案用於研究與臨床影像分析流程演示；請遵守機構 IRB／資料使用規範。

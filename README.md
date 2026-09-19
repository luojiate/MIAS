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
| Database | MongoDB `mongodb://127.0.0.1:27017`，資料庫名 `mias` |
| 推論 | ONNX Runtime：`efficientTransUnetB3_inner.onnx` + `efficientTransUnetB0_outer.onnx` |

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
uv run python -m unittest tests.test_preprocess -v
```

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

新增分析頁可切換「原圖 / 預測面積」；個人頁可回看疊圖與量測。

## API（cookie session）

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/login` | no | `{ email, password }` → `{ message, user }` |
| POST | `/logout` | no | 清除 session cookie |
| POST | `/register` | no | `{ name, email, password }`；email 重複 → 400 |
| POST | `/upload-image` | yes | multipart `image` → 量測 + 疊圖 URL（`overlay` 等） |
| POST | `/create` | yes | 儲存分析（含影像／疊圖資訊） |
| GET | `/personal` | yes | 目前使用者的分析列表 |
| DELETE | `/delete/{id}` | yes | 僅擁有者可刪 |

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
start-local.bat    Windows 一鍵啟動
```

## 環境變數（常用）

見 `backend/.env.example`：

- `MONGO_URI` / `MONGO_DB` / `SESSION_SECRET` / `PUBLIC_URL`
- `MIAS_INNER_ONNX` / `MIAS_OUTER_ONNX`
- `MIAS_INFER_SIZE`（預設 256）
- `MIAS_MASK_THRESH`（預設 0.5）
- `MIAS_ORT_PROVIDERS`

## License / 備註

本專案用於研究與臨床影像分析流程演示；請遵守機構 IRB／資料使用規範。
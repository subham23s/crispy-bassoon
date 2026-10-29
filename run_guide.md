# 🚀 CyberSecRA-X — Step-by-Step Run Guide

## Quick Start (One-Click)

**Just double-click [`start.bat`](file:///d:/CyberSecRA-X/start.bat)** in the project root. It handles everything and opens the dashboard automatically.

---

## Manual Step-by-Step

### Step 1: Create Virtual Environment
```powershell
cd d:\CyberSecRA-X
python -m venv .venv
```

### Step 2: Activate the Virtual Environment
```powershell
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install Python Dependencies
```powershell
pip install --upgrade pip
pip install -r backend\requirements.txt -r backend\requirements-documents.txt
```

### Step 4: Install Frontend Dependencies
```powershell
npm ci --prefix frontend
```

### Step 5: Configure Environment
```powershell
.\.venv\Scripts\python.exe scripts\product.py configure
```
> [!NOTE]
> This creates a `.env` file from `.env.example` with auto-generated secrets. Only runs once — skips if `.env` already exists.

### Step 6: Build the Frontend
```powershell
.\.venv\Scripts\python.exe scripts\product.py build
```

### Step 7: Start the Project 🎉
```powershell

```

This will:
1. Start the **backend API** on `http://localhost:8000`
2. Start the **frontend dashboard** on `http://localhost:3000`
3. **Automatically open the dashboard** in your default web browser

> [!TIP]
> To suppress auto-browser-open, add `--no-open`:
> ```powershell
> .\.venv\Scripts\python.exe scripts\product.py up --no-open
> ```

### Step 8: Stop the Project
```powershell
.\.venv\Scripts\python.exe scripts\product.py down
```

### Check Status
```powershell
.\.venv\Scripts\python.exe scripts\product.py status
```

---

## All Available Commands

| Command | Description |
|---------|-------------|
| `product.py configure` | Creates `.env` with auto-generated secrets |
| `product.py setup` | Full setup: venv + pip + npm |
| `product.py build` | Builds the Next.js frontend |
| `product.py up` | Starts backend + frontend, opens browser |
| `product.py up --no-open` | Starts without opening browser |
| `product.py up --no-build` | Starts without rebuilding frontend |
| `product.py down` | Stops all services |
| `product.py status` | Shows running service PIDs |
| `product.py test` | Runs pytest + typecheck + lint |

---

## Ports

| Service | URL |
|---------|-----|
| Frontend Dashboard | `http://localhost:3000` |
| Backend API | `http://localhost:8000` |
| API Health Check | `http://localhost:8000/health` |
| API Readiness | `http://localhost:8000/ready` |

---

## Troubleshooting

> [!WARNING]
> If you get "Product is already running", run `product.py down` first, then `product.py up`.

> [!WARNING]
> If port 3000 or 8000 is in use, stop whatever is using it, or set `PORT` and `WEB_PORT` in your `.env` file.

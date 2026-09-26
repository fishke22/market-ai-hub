# AI Reconstruction Guide

給未來 AI Agent（ChatGPT / Codex / Claude / DeepSeek / OpenCode）重建整套系統。不假設你讀過專案歷史。

可移植性目前逐格 truth 先讀 `docs/development/W7_PORTABILITY_ACCEPTANCE.yaml`。其中 `PASS` 只代表該驗收格在其明示 scope 內已有證據；`UNVERIFIED_EXTERNAL_GATE`、`WAITING_TIME_WINDOW` 等未通過格不得被總結成「完整移機完成」。
新 Windows / WinCred / certificate / COM / full dependency install 的只讀盤點可跑：
```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_external_relocation_gates.ps1 -Json
```
此工具永遠不會自行把 external gate 升成 PASS，也不安裝套件、不寫 WinCred、不匯入/匯出憑證、不註冊 COM、不登入券商。

## STEP 1 — Clone repository
```bash
git clone <repo-url> MARKET_AI_HUB
cd MARKET_AI_HUB
```
- expected：看到 `README.md`、`SYSTEM_MANIFEST.yaml`、`docs/`、`src/`、`config/`。
- failure：確認 repo 不含 weights/data（見 `PUBLICATION_EXCLUDE_MANIFEST.txt`）。

## STEP 2 — Inspect SYSTEM_MANIFEST
讀 `SYSTEM_MANIFEST.yaml`（machine-readable 能力/架構/target/安全）。讀 `config/capabilities.yaml`（feature 狀態）。

## STEP 3 — Check OS / Python / GPU
- Windows x64；主環境只接受 CPython 3.11/3.12 **64-bit**。V1 freeze 為 Python 3.12.13。
- 不要用 `platform.machine()` 判 Python bitness；32-bit Python 在 64-bit Windows 也可能回 `AMD64`。正式 installer 以 pointer width 驗證。
- CUDA GPU（RTX 4060 Ti 16GB 或等效）是模型加速項；無 GPU 仍可跑 CPU fallback，但 heavy model 較慢。

## STEP 4 — Create environment
```powershell
# 只驗 Python 選擇 + 建立新 venv，不下載任何 dependency：
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -BootstrapOnly

# 如需明確指定 interpreter：
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -BootstrapOnly -PythonExe "<python.exe>"
```
- installer 會優先從 Windows Python Launcher 枚舉 3.12/3.11 x64，拒絕 32-bit 或 3.13+。
- `-BootstrapOnly` 不執行 pip install；適合先做新路徑/新 venv 無下載驗收。
- source relocation 可重現 smoke：`scripts\verify_source_relocation_bootstrap.ps1`。它只複製 Git tracked files 到 temp 新路徑、建立 bootstrap venv，並驗證新程序不依賴原 checkout。

## STEP 5 — Install dependencies
```powershell
pip install -r requirements-runtime.txt
# dev（tests）：
pip install -r requirements-dev.txt
```
- failure：依賴衝突（如 FinCast 需 tensorflow/jax）→ 隔離獨立 venv，不要塞核心環境（見 `docs/reference/DEPENDENCIES.md`）。

## STEP 6 — Download models
```powershell
python scripts/download_models.py --check     # 看缺哪些
python scripts/download_models.py --required  # 只下 required
python scripts/download_models.py --list
python scripts/download_models.py --optional  # 使用者自選
```
- weights 永遠不進 Git；由 Hugging Face 下載並 pin revision（`config/model_manifest.yaml`）。

## STEP 7 — Configure optional API keys
複製 `.env.example` → `.env`，填需要用的（FRED / FinMind / BEA / e-Stat / EIA / EDINET）。
- 不填也能跑；只影響對應 provider（標 NEEDS_CONFIG）。

## STEP 8 — Initialize Data Lake
```powershell
python -c "from market_ai_hub.automation.data_lake import DataLakeManager; DataLakeManager()"
```
- expected：`data/` 出現 raw/normalized/features/predictions/analysis_archive/cache/manifests。

## STEP 9 — Run validation
```powershell
pytest tests/
```
- expected：全 PASS（live tests 預設排除，`-m live` 才跑網路）。

## STEP 10 — Start MCP Server
```powershell
.venv\Scripts\market-ai-mcp.exe
# 或
python -m market_ai_hub.mcp.server
```

## STEP 11 — Install / import MCP config
不要手動替換 `<PROJECT>`。先由目前 checkout 產生 relocation-safe client JSON：
```powershell
python scripts\render_mcp_config.py --client generic --require-command
python scripts\render_mcp_config.py --client cherry --require-command
```
預設只輸出 stdout；若要寫到暫存/匯入檔，明確加 `--output <path>`。`--project-root <path>` 可用於搬移驗收。產生器只建立 JSON，不會自動修改 Cherry Studio 或其他 MCP client 設定。

## STEP 12 — Install Skills
複製 `skills/{name}/` 到你的 Agent 平台（Cherry Studio / 手動當 instruction reference）。

## STEP 13 — Run first Osaka Micro analysis
MCP 呼叫 `get_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES")`。
- expected：`execution_target = OSE_NIKKEI225_MICRO_FUTURES`、`reference_price_type = SETTLEMENT`（若有官方 settlement）。

## STEP 14 — Enable optional Research Scheduler
先用 dry-run 檢查搬移後的 task action 是否已綁定目前 checkout：
```powershell
scripts\register_research_tasks.ps1 -DryRun
scripts\register_forward_shadow_task.ps1 -DryRun
```
確認 JSON 內 `repo_root`、`execute` / `arguments`、`working_directory` 都指向目前專案路徑，且沒有舊 checkout 後，再由使用者明確執行：
```powershell
scripts\register_research_tasks.ps1   # OPT-IN（不自動註冊）
scripts\register_forward_shadow_task.ps1   # OPT-IN；重新執行預設會刷新舊 task 路徑
```
若特別要保留已存在的 forward-shadow task，可加 `-PreserveExisting`；搬移驗收時不要使用此選項，否則可能保留舊路徑。

## STEP 15 — Verify Prediction Registry / Archive
MCP 呼叫 `get_analysis_archive_status` / `get_forward_test_status`。

## STEP 16 — Optional integrations
- TradingView：OPTIONAL，未安裝（`docs/integrations/TRADINGVIEW_OPTIONAL_BRIDGE.md`）。
- Yuanta：RESERVED_QUOTE_ONLY，realtime recorder = false（`docs/YUANTA_DATA_CAPABILITY_MATRIX.md`）。

## STEP 17 — Yuanta integration restoration（證券 ≠ 期貨；三條 path）

先讀 `docs/YUANTA_SETUP_AND_LOGIN.md` + `docs/YUANTA_API_ARCHITECTURE.md`。

**Yuanta prerequisites（不能假設 clone 就含 proprietary binaries）：**
1. Apply API permission（期貨 SPARK 權限 / API 行情 / API 交易，各別申請）
2. Obtain official component（SPARK x64 / Futures Quote OCX，官方頁下載）
3. Install .NET 8 for SPARK（`dotnet --list-runtimes` 確認 8.x）
4. Import certificate into Windows 11 when required（`docs/YUANTA_CERTIFICATE_WINDOWS11.md`）
5. Verify certificate（`scripts/check_yuanta_certificate.ps1`）
6. Setup WinCred account preset（`MARKET_AI_HUB/YUANTA/FUTURES`、`/SECURITIES`）
7. Setup x86 legacy quote sidecar if used（`scripts/setup_yuanta_futures_x86.ps1`）。預設透過 Windows `py -3.11-32` 找 32-bit Python；若 launcher 不可用，可設定 `MARKET_AI_PYTHON_X86` 或傳 `-PythonX86 <path>`，不得寫死特定使用者目錄。
8. Run diagnostics（`scripts/check_yuanta_futures_com.ps1` → READY_FOR_AUTH）。診斷 script 以自己的 repo root 建 `PYTHONPATH`，不得依賴 `D:\MARKET_AI_HUB`。
9. Manual getpass auth（`scripts/yuanta_futures_auth.ps1` / `auth_probe --profile securities`）
10. Verify quote capability（auth 成功後）

**下載/憑證/權限/商品代碼：**
- `docs/YUANTA_DOWNLOADS.md`、`docs/YUANTA_CERTIFICATE_WINDOWS11.md`
- `docs/YUANTA_API_PERMISSIONS.md`、`docs/YUANTA_MARKET_DATA_PERMISSIONS.md`
- `docs/YUANTA_PRODUCT_CODE_LOOKUP.md`、`config/yuanta_product_codes.yaml`

**不要重走錯路**：期貨帳號 SPARK Login 回 0112 = 「無此權限使用功能」（需另申請期貨 SPARK 權限），
不是「Wrong API family」。Legacy COM 是另一套 API（官方頁命名「國內行情 API」，scope 疑 DOMESTIC_ONLY）。

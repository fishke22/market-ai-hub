# GITHUB PUBLICATION REPORT

日期：2026-09-19
Gate：**PUBLICATION_COMPLETE**

---

## 1. GitHub account

`fishke22`（由 `gh api user` 取得；未猜測）。

## 2. Repository URL

https://github.com/fishke22/market-ai-hub

## 3. Visibility

**PUBLIC**

## 4. main branch

`main`（已推送；remote HEAD 與 local HEAD 一致）。

## 5. Freeze tag

`v1-freeze-2026-09-19`（指向 commit `d9dbe36c63046c16b1ada77de34a3b6dd4cfe548`）

## 6. GitHub Release URL

https://github.com/fishke22/market-ai-hub/releases/tag/v1-freeze-2026-09-19

## 7. Commit hash

`d9dbe36c63046c16b1ada77de34a3b6dd4cfe548`

## 8. Freeze build_id

- **發布 build_id：`bbf3cb2f9a80d20e`**
- 發布前本機驗收 build：`4742a33e5b17d1d0`

變更原因（不改變研究邏輯）：
1. **可攜性修復**：移除 `mcp/server.py` 硬編碼 `D:\MARKET_AI_HUB\logs` 路徑（改由專案根目錄推導），
   否則其他機器 clone 後 MCP 啟動會失敗。
2. **換行正規化**：所有文字檔統一 LF（`.gitattributes`），確保任何機器 clone 得到相同位元組 → 相同 build_id。

## 9. Test result

| 項目 | 結果 |
|------|------|
| 本機 pytest（全部） | **154 passed** |
| 本機 MCP smoke | PASS（13 tools） |
| clean clone 輕量測試 | **134 passed**（20 integration deselected） |
| clean clone MCP health_check | status=ok、build_id 相符 |

## 10. Clean restore result

**PASS**。實際流程（不使用原始 working tree）：
1. `git clone --branch v1-freeze-2026-09-19` 到 Windows TEMP 全新目錄。
2. `uv venv` + `uv pip install -r requirements-runtime.txt` + `pip install -e .` + dev deps。
3. `import market_ai_hub` → build_id **`bbf3cb2f9a80d20e`**（與凍結值相符）。
4. `pytest -m "not integration and not live"` → 134 passed。
5. 啟動 MCP（clone 內 `.venv\Scripts\market-ai-mcp.exe`）→ 13 tools。
6. `health_check` → status=ok、build_id 相符、chronos/timesfm ready、duckdb/yfinance ok。
7. `source_root` 指向 clone 的 TEMP 路徑（證明不是原工作目錄）。

> 模型 cache 重用：以目錄 junction 指向既有 `models/cache`（**已揭露**）。
> 全新機器若無 cache，執行 `scripts\download_models.py --download` 即可。

## 11. Python version

3.12.13（x64）。V1 Freeze 環境快照見 `docs/environment/V1_FREEZE_ENVIRONMENT.txt`。

## 12. Torch / CUDA

`torch 2.14.0+cu130`，`torch.version.cuda = 13.0`，`cuda_available=True`，
GPU = NVIDIA GeForce RTX 4060 Ti 16GB，driver 616.56。（無 GPU 亦可 CPU 執行。）

## 13. Required dependencies

見 `docs/DEPENDENCIES.md` §B 與 `requirements-runtime.txt`（numpy/pandas/scikit-learn/xgboost/
lightgbm/duckdb/pyarrow/yfinance/httpx/mcp/pydantic/exchange-calendars/chronos-forecasting/timesfm/torch …）。
精確傳遞依賴：`requirements-lock-windows-x64.txt`。

## 14. Optional dependencies

FinCast（隔離 `.venv-fincast`，非必需）、NVIDIA GPU、`FINMIND_TOKEN`、`FRED_API_KEY`。

## 15. Model manifest

`config/model_manifest.yaml`：
- chronos-2（amazon/chronos-2, rev `29ec3766…`, Apache-2.0, ~456MB, required）
- timesfm-3.0（google/timesfm-3.0-pytorch, rev `43046b85…`, 非商業授權, ~1262MB, required）
- fincast（Vincent05R/FinCast, rev `2d7d90b1…`, Apache-2.0/repo, ~3967MB, optional）

## 16. Security scan result

**CLEAN**（0 findings）。掃描範圍：所有文字檔（.py/.md/.json/.yaml/.toml/.ps1/.txt/.example 等），
檢查 GitHub/OpenAI/HF/AWS token、Bearer、private key、assignment secret、email、Windows 使用者路徑。
另移除 2 處個人絕對路徑（`C:\Users\fishk\…`，FinCast 相關）改為可攜解析。

## 17. Files intentionally NOT uploaded

| 類別 | 說明 |
|------|------|
| `.env` / secrets | 不存在；僅 `.env.example`（空 placeholder） |
| `.venv` / `.venv-fincast` | 由 `setup_windows.ps1` 重建 |
| `models/cache` | 模型 weights（依 license，需自行下載） |
| `data/` | DuckDB / Parquet 市場資料（僅保留 `data/.gitkeep`） |
| `logs/` / `reports/` | 執行期輸出 |
| `external/fincast/` | 第三方 repo clone（有 nested .git；按需 clone） |
| `.remediation_backup_20260919/`、`.opencode/`、`environment_export/` | 本機備份 / 暫存 |

## 18. Third-party licensing warnings

- **TimesFM-3.0 weights 為非商業授權**（`timesfm-non-commercial-license-v1.0`）：禁止商業部署與重新散布。
- **FinCast**：官方 README 標示 research/education。
- **模型 weights 一律不隨 repository 散布**（`THIRD_PARTY_NOTICES.md`）。
- 本 repository 公開可讀，但**專案自身授權尚未另行指定**（未附 LICENSE）。

## 19. Backup / restore instructions location

- `docs/BACKUP_AND_RESTORE.md`（從零還原 Step by Step）
- `docs/INSTALL_WINDOWS.md`（給非工程師的詳細安裝）
- `scripts/create_offline_backup.ps1`、`scripts/export_environment.ps1`

## 20. Remaining limitations

1. **`.github/workflows/ci.yml` 未推送**：gh 的 OAuth token 缺 `workflow` scope，
   無法推送 workflow 檔案（GitHub 政策）。檔案已存在本機，待使用者執行：
   ```powershell
   gh auth refresh -s workflow
   cd D:\MARKET_AI_HUB
   git add .github/workflows/ci.yml
   git commit -m "Add CI workflow"
   git push origin main
   ```
2. `MODEL_PREDICTIVE_GATE` / `TRADING_EDGE_GATE` 仍為 **UNPROVEN**（非「已證明獲利」）。
3. 大阪日經為 ^N225 INDEX proxy，非 OSE 微型期貨即時。
4. TS 模型 UNVALIDATED；分類器 probability 未 calibration。
5. FX session 為簡化模型；期貨 proxy session=unknown。
6. `model_revision` 離線時可能為 `unknown`。

## Gate 判定

| 條件 | 結果 |
|------|------|
| security scan clean | ✅ 0 findings |
| tests pass | ✅ 154（本機）/ 134（clean clone 輕量） |
| push success | ✅ main 已推送 |
| public repository verified | ✅ PUBLIC，remote HEAD 一致 |
| release created | ✅ v1-freeze-2026-09-19 |
| clean restore test passed | ✅ clone → venv → deps → tests → MCP → health_check |

**PUBLICATION_COMPLETE**

（唯一待辦：使用者以 `gh auth refresh -s workflow` 後推送 CI workflow；不影響程式碼可用性。）

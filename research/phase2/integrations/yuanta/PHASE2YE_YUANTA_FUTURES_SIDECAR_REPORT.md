# Phase 2Y-E — Yuanta Futures x86 Sidecar Completion + Real Auth + OSE Micro Quote Probe

- Gate: **PHASE2YE_READY_FOR_USER_AUTH**（x86 sidecar + COM + STA/message pump 全 ready；真實 login 待使用者本機 getpass）
- build_id：`ccabe1e1552d9ae7`（未變）
- 測試：**449 passed**（430 + 19 2Y-E；5 live deselected）

## x86 Python / pywin32 / comtypes
- 32-bit Python 3.11（`Python311-32`）→ `.venv-yuanta-futures-x86` 已建立。
- comtypes + pywin32 已安裝（minimal，**無** torch/Chronos/TimesFM/pandas/pyarrow）。
- sidecar import：`futures_auth_probe` 乾淨 import（**0** heavy module）。

## OCX / COM registration
- `YuantaQuote_v2.1.2.9.ocx`（32-bit ActiveX），ProgID `YUANTAQUOTE.YuantaQuoteCtrl.1`，
  CLSID `{8E7FB42A-...}`，WOW64 已註冊（InprocServer32 正確）。

## STA / message pump（實測）
- `pythoncom.CoInitializeEx(COINIT_APARTMENTTHREADED)` + 隱藏 window +
  `AtlAxCreateControlEx` + `GetBestInterface` + `GetEvents` + bounded `PumpWaitingMessages`。
- `CoUninitialize` 於 finally。
- **實測 smoke：`SMOKE_OK`**（connect + ActiveX + event sink + cleanup 全通過，無 GUI/wx）。

## sidecar import / 隔離
- `futures_com.py` / `futures_auth_probe.py` 只 import stdlib + comtypes + pywin32 + minimal project module，
  不拉 numpy/pandas/pyarrow/torch。

## auth（READY，未執行真實 login）
- `scripts\yuanta_futures_auth.ps1` → `futures_auth_probe`（WinCred preset → masked → getpass →
  SetMktLogon T/T+1 → bounded pump 等 OnMktStatusChange → sanitize → disconnect）。
- 單次 login、不 retry、password 只 process memory（`del password`）。

## OSE Micro symbol: UNRESOLVED
- COM quote interface 方法盤點（24 methods）：**無「商品清單」方法**，無法從 runtime 列舉 OSE Micro symbol。
- 不猜 TradingView/JPX code。`futures_quote_probe` 需 verified `--symbol` 才註冊。

## quote probe（READY，auth 成功後）
- `scripts\yuanta_futures_quote_probe.ps1` → 登入 → AddMktReg 單一商品 → bounded 8s 報價 →
  DelMktReg → disconnect。非 recorder。

## Security: PASS
- OrderApiExposureGuard PASS；quote-only；masked account；password 不落檔；secret scan 無真實 PII。

## Docs / scripts
- `scripts/setup_yuanta_futures_x86.ps1`（一鍵重建 sidecar，不登入）
- `scripts/check_yuanta_futures_com.ps1`（唯讀檢查 → **RESULT: READY_FOR_AUTH**）
- `scripts/yuanta_futures_auth.ps1` / `scripts/yuanta_futures_quote_probe.ps1`
- `docs/YUANTA_SETUP_AND_LOGIN.md` / `YUANTA_API_ARCHITECTURE.md` / `YUANTA_FUTURES_COM.md` /
  `YUANTA_SECURITIES_SPARK.md` / `YUANTA_FUTURES_ERROR_CODES.md` 已更新（含 script 步驟）。

## Tests（19 新增）
x86_sidecar_is_32bit_contract / minimal_dependencies / no_ml_import / sta_required /
message_pump_bounded / auth_timeout / auth_event_required / auth_single_attempt / auth_cleanup /
account_from_wincred / account_masked / password_getpass / password_not_persisted /
quote_max_duration / quote_one_symbol_only / delmktreg_cleanup / setup_script_present /
diag_script_present / docs_reconstructable。

## Blockers（下一步，需使用者）
- 使用者本機執行 `powershell -ExecutionPolicy Bypass -File scripts\yuanta_futures_auth.ps1`，
  getpass 輸入密碼一次 → `YUANTA_FUTURES_AUTH_RESULT.json`。
- auth 成功後，OSE Micro symbol 仍需外部來源（COM 無商品清單 API）。

## 驗證
- `pytest tests/ -q` → 449 passed
- `scripts\check_yuanta_futures_com.ps1` → READY_FOR_AUTH
- 32-bit sidecar `connect()` smoke → SMOKE_OK
- build_id 維持 `ccabe1e1552d9ae7`
- 全程未下單/查帳/持倉/餘額/損益；未 Recorder；未 Live Trading；未 GitHub push。

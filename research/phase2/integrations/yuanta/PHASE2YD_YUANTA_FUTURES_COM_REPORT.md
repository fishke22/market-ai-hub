# Phase 2Y-D — Yuanta Futures COM Interop + Real Futures Auth + OSE Symbol/Quote Probe

- Gate: **PHASE2YD_COM_BLOCKED**（32-bit ActiveX OCX 需隔離 32-bit sidecar；code/venv 已備，真實 login 待使用者）
- build_id：`ccabe1e1552d9ae7`（未變）
- 測試：**430 passed**（415 + 15 2Y-D；5 live deselected）

## Securities Spark: AUTH VERIFIED
- 證券 `YuantaSparkAPITrader`（pythonnet/.NET 8）真實 Login `MsgCode=0001` 成功（Phase 2Y-C）。

## Futures API family: COM VERIFIED
- 期貨 = legacy COM Quote API，**非 Spark**。
- 期貨帳號用 Spark Login 回 0112（= Wrong API family）。

## COM component
- `YuantaQuote_v2.1.2.9.ocx`（ActiveX control），version 2.1.2.9。
- ProgID `YUANTAQUOTE.YuantaQuoteCtrl.1`、CLSID `{8E7FB42A-1137-467E-98C6-830C9B02EA82}`、
  TypeLib `{350F911B-4F62-42AF-BCD5-83B431A4BBDF}`。
- 路徑 `C:\Yuanta\QAPI\YuantaQuote_v2.1.2.9.ocx`。

## Architecture: x86（32-bit）
- OCX 註冊於 WOW64（32-bit view）；ThreadingModel=Apartment（STA）。
- **需 32-bit Python sidecar**；主 MARKET_AI_HUB 維持 x64。

## Registration: PASS
- 已註冊（`registered_32bit=true`，InprocServer32 = OCX 路徑）。

## Real futures login: NOT_RUN
- 登入流程已寫（`SetMktLogon` T 盤 80 / T+1 盤 82，事件 `OnMktStatusChange`）。
- 需使用者在 32-bit sidecar 本機 getpass 執行，我不得代為登入。

## OSE Micro code: UNRESOLVED
- 需 login 後用 COM read-only 商品機制解析；不猜 TradingView/JPX code。

## Quote: NOT_TESTED
- `AddMktReg` / `DelMktReg` 已寫，未實測。

## Security: PASS
- OrderApiExposureGuard PASS（futures_com.py 無 order method）；quote-only；masked account；
  password 只 process memory；secret scan 無真實 PII。

## Docs: COMPLETE
- `docs/YUANTA_API_ARCHITECTURE.md`（分流總表 + 決策樹）
- `docs/YUANTA_SECURITIES_SPARK.md`（Spark 已驗證）
- `docs/YUANTA_FUTURES_COM.md`（COM 32-bit OCX）
- `docs/YUANTA_SETUP_AND_LOGIN.md`（總導航，第一頁決策樹）
- `docs/YUANTA_FUTURES_ERROR_CODES.md`（只寫已驗證）

## 已交付
- `integrations/yuanta/futures_com.py`（`YuantaFuturesQuoteClient`，quote-only）
- `integrations/yuanta/futures_auth_probe.py`（CLI）
- `integrations/yuanta/futures_com_diag.py` → `YUANTA_FUTURES_COM_DIAGNOSTIC.json`
- `.venv-yuanta-futures-x86`（32-bit Python + comtypes，已建立）
- SYSTEM_MANIFEST / capabilities / PUBLICATION_FILE_MANIFEST / AI_RECONSTRUCTION_GUIDE 更新
- 15 unit tests

## Blockers（精確）
1. 32-bit OCX 需隔離 32-bit sidecar（venv 已建，但 sidecar 尚需 pywin32 + 完整 package import）。
2. ActiveX 需 window handle + STA message pump（futures_com.py 已寫，未 runtime 驗證）。
3. 真實 login 需使用者本機 getpass（我不得代登入）。

## 下一步（使用者）
1. sidecar 補 pywin32 + package：`.venv-yuanta-futures-x86\Scripts\pip install pywin32`
2. sidecar 執行 `python -m market_ai_hub.integrations.yuanta.futures_auth_probe`（需 src path）
3. auth 成功後再 `futures_quote_probe --instrument OSE_NIKKEI225_MICRO_FUTURES`

## 驗證
- `pytest tests/ -q` → 430 passed
- `futures_com_diag` → registered_32bit=true、x86、READY_32BIT_SIDECAR
- build_id 維持 `ccabe1e1552d9ae7`
- 全程未下單/查帳/持倉/餘額/損益；未 Recorder；未 Live Trading。

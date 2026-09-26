# Yuanta Quick Start — Windows 11（照做）

> 給全新 Windows 11、完全不懂的人。每一步：command / expected / failure handling。

## 0. 先懂一件事
元大 API 是**四套**：SPARK（證券+期貨）、Futures Legacy Quote COM（期貨行情）、
Futures Legacy Trading（期貨交易）、**Leveraged Trading「槓桿全球贏家」Web API（CFD，獨立槓桿帳戶）**。
**不要混用。** 見 `docs/YUANTA_API_ARCHITECTURE.md`。

⚠️ **不要到「槓桿全球贏家」API 申請頁（`ltm.yuantafutures.com.tw/member/api-apply`）申請一般 Futures API。**
OSE Micro / JNU 是 JPX Futures，應走一般 Futures / SPARK 路徑。

## 1. 申請 API permissions
- 期貨線上服務 → 線上服務 → API 行情服務 / API 交易服務申請聲明書。
- expected：營業員確認開通。
- failure：未開通 → 各 API 回 0112 / 無登入權。

## 2. 下載元件
- SPARK：元大證券 API 專區 → Python Windows x64（本專案主用）。
- Futures 行情：元大期貨 API 頁（行情 API，公開頁 2.1.2.7；本機 observed 2.1.2.9）。
- Futures 交易：交易 API 1.6.1.3（FUTURE_RESEARCH_ONLY，不下載也可）。
- expected：解壓得到 `YuantaSparkAPI.dll` / `YuantaQuote_v2.1.2.9.ocx`。
- failure：找不到頁面 → 見 `docs/YUANTA_DOWNLOADS.md`。

## 3. 下載/申請憑證
- 元大官方憑證中心（申請/更新/匯出/匯入）。
- expected：取得正式憑證備份檔（PFX）。
- failure：同一 ID 只能一張有效憑證。

## 4. 匯入 Windows 11
- Chrome → Settings → Privacy and security → Security → Manage certificates →
  Manage certificates imported from Windows → Import → 選備份檔 → Wizard 完成。
- expected：匯入成功。
- failure：見 `docs/YUANTA_CERTIFICATE_WINDOWS11.md`。

## 5. 驗證憑證
```
powershell -ExecutionPolicy Bypass -File scripts\check_yuanta_certificate.ps1
```
- 這只做 generic Windows certificate-store preflight；`certificate_store_has_unexpired: true` **不等於**元大憑證已驗證。
- 正式 acceptance：到元大憑證中心做「憑證簽驗」且成功；repo 腳本不會讀 subject/thumbprint/private key 來猜身份。

## 6. 安裝 SPARK prerequisites
- .NET 8 x64（`dotnet --list-runtimes` 確認 8.x）。
- 主 venv：`pythonnet`。
- expected：`python -m market_ai_hub.integrations.yuanta.spark_runtime_probe` → `READY`。

## 7. 安裝 Legacy quote x86 sidecar（若需要）
```
powershell -ExecutionPolicy Bypass -File scripts\setup_yuanta_futures_x86.ps1
```
- expected：`RESULT: READY_FOR_AUTH`。
- 預設：用 Windows `py -3.11-32` 找 32-bit Python。
- 若 Python 放在自訂路徑：設定 `MARKET_AI_PYTHON_X86`，或使用 `-PythonX86 "<python.exe>"`；不要修改 script 寫死使用者目錄。
- failure：缺 32-bit Python → 安裝 Python 3.11 32-bit；指定錯誤/非 32-bit interpreter 時會在安裝依賴前停止。

## 8. 設定 WinCred
- 期貨/證券帳號 preset + **Legacy 登入ID**（身份證ID，不是期貨帳號）：
```
powershell -ExecutionPolicy Bypass -File scripts\setup_yuanta_legacy_login_id.ps1
```
- expected：masked 顯示已存。
- failure：無 WinCred → 見 `docs/YUANTA_SECURITY.md`。

## 9. 執行 diagnostics
```
powershell -ExecutionPolicy Bypass -File scripts\check_yuanta_futures_com.ps1
```
- expected：`READY_FOR_AUTH`。

## 10. 執行人工 auth
- 證券：`.venv\Scripts\python.exe -m market_ai_hub.integrations.yuanta.auth_probe --profile securities`
- 期貨行情：`powershell -ExecutionPolicy Bypass -File scripts\yuanta_futures_auth.ps1`
- expected：證券 `MsgCode=0001`；期貨 T+1 `登入成功`。
- failure：0112 / 無登入權 → 見 `YUANTA_PERMISSION_CONTRADICTION_REPORT.md` + `YUANTA_SUPPORT_EVIDENCE_PACKET.md`。

## 11. 確認 market entitlement
- 海外（OSE/JNU）行情需向營業員確認是否開通/收費。

## 12. 查商品代碼
- `config/yuanta_product_codes.yaml`（JNU=大阪微日經 public code）。
- **四種代碼分離**：public / SPARK StkCode / COM symbol / order code，不互等。

## 13. quote probe
- auth 成功 + symbol verified 後：
  `powershell -ExecutionPolicy Bypass -File scripts\yuanta_futures_quote_probe.ps1`

## 14. 不要啟用 Trading API execution
- Trading API（1.6.1.3）FUTURE_RESEARCH_ONLY；**本系統 PROHIBITED_IN_PHASE2**。

## Troubleshooting Table（未來 AI 直接查）
| 問題 | 意義 |
|---|---|
| Spark Securities 0001 | success |
| Spark Futures 0112 | 不直接下結論；走 permission/profile/account 矛盾流程 |
| Legacy Quote Status=1 | connected only（等待登入） |
| Legacy Quote Status=2 | authenticated（登入成功） |
| T 成功 / T+1 失敗 | session-specific diagnosis |
| T+1 成功 / T 失敗 | session-specific diagnosis |
| JNU 註冊失敗 | public product code ≠ quote symbol |
| 找不到商品列表 | runtime API may not expose list |

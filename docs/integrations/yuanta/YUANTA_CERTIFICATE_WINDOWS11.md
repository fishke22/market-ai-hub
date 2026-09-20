# Yuanta Certificate — Windows 11（元大憑證完整流程）

> 元大憑證**不是** MARKET_AI_HUB 自行產生。從「元大官方憑證中心」申請/更新/匯出/匯入。

## 官方原則（元大憑證中心）
- 同一身分證字號只能申請**一張有效憑證**。
- 同一人在元大開立的**證券 + 期貨電子戶**可使用同一張憑證。
- 有效期限目前 **1 年**。

## 方式 A：元大官方網頁 / Chrome 操作流程
```
Chrome
→ Settings
→ Privacy and security
→ Security
→ Manage certificates
→ Manage certificates imported from Windows
→ Import
→ 選擇「使用者自己的正式憑證備份檔」
→ 依 Windows Certificate Import Wizard 完成匯入
```

⚠️ 不要在本文件放：真實 PFX、憑證密碼、身分證字號。
⚠️ 若官方 screenshot 可確認 store selection → 照官方流程寫；不能確認 → **不猜 store**。

## 匯入後驗證
到「元大期貨憑證中心」→「憑證簽驗」，檢查：
- 安控元件
- 憑證簽驗

**只有簽驗正常，才進交易 API troubleshooting。**

## 本機檢查腳本
```
scripts\check_yuanta_certificate.ps1
```
- 只檢查：有沒有可用憑證 / expiry / Windows store access。
- **不** export private key、不顯示完整 subject / 身分證、不讀 private key。
- 輸出：`certificate_present` / `certificate_valid` / `days_until_expiry`（PII 全遮罩）。

## 憑證需求 matrix（不要寫過度廣泛）
| 流程 | 憑證需求 |
|---|---|
| SPARK Securities | 依正式 API 文件 |
| SPARK Futures | 依正式 API 文件 |
| Legacy Futures Quote COM | 依官方 Quote API 文件/實測；無證據 → `NOT_CONFIRMED_REQUIRED` |
| Legacy Futures Trading API | 依官方 Trading API 文件 |
| MultiCharts ordering | 官方明確要求匯入憑證 |

**若某 quote-only flow 沒有證據需要 certificate → 寫 `NOT_CONFIRMED_REQUIRED`，不要猜。**

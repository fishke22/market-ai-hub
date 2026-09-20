# Yuanta Permission Contradiction Report（權限矛盾診斷）

> 使用者 authoritative fact：「**元大期貨 API 權限已經全部開通。**」
> 因此 server 回無權限時，不得直接寫 NEEDS_PERMISSION，必須先做 contradiction diagnosis。

## 權限矩陣（USER vs SERVER）

| 權限 | 使用者確認 | 實際 server/API 回應 | 狀態 |
|---|---|---|---|
| SPARK_SECURITIES | enabled | `MsgCode=0001` | **SERVER_CONFIRMED** |
| SPARK_FUTURES | enabled | `0112` | **CONTRADICTION** |
| LEGACY_QUOTE_T | enabled | `無登入權` | **CONTRADICTION** |
| LEGACY_QUOTE_TPLUS1 | enabled | `登入成功`(status=2) | **SERVER_CONFIRMED** |
| LEGACY_TRADING_T / T+1 | — | 未測 | NOT_TESTED |
| OVERSEAS_MARKET_DATA | — | — | UNKNOWN |
| OSE_MARKET_DATA | — | — | UNKNOWN |

## 矛盾清單（不自行猜原因，只列證據）

### 矛盾 1：SPARK Futures 0112（未解）
- user says：期貨 API 權限全開。
- runtime says：`0112`（無此權限使用功能）。
- 狀態：**CONTRADICTION**（待營業員確認 SPARK Futures entitlement）。

### 已解：Legacy Quote T 盤「無登入權限」
- **登入ID bug 已修正**：官方 sample 的 login 欄位是「登入ID」（身份證ID），不是期貨帳號。
- 使用者以正確登入ID（masked `L1******96`）重測：
  - T+1 盤：`登入成功`（status=2）→ SERVER_CONFIRMED。
  - T 盤：`使用者無登入權限`（status=-2）→ **SERVER_DENIED（正確ID下仍拒）**。
- 結論：**SESSION_PERMISSION_ASYMMETRY**（T+1 有權限、T 無權限）→ 需營業員確認 T 盤行情權限。

## 登入 ID 修正（本棒完成）
- `legacy_login_id` 與 `futures_account` 永久分離 ✅。
- WinCred target `MARKET_AI_HUB/YUANTA/LEGACY_LOGIN_ID` ✅（已 preset，masked `L1******96`）。
- `scripts/setup_yuanta_legacy_login_id.ps1` ✅（已修 SyntaxError，改為呼叫 module）。
- `futures_auth_probe` 改用 login_id 登入 ✅。

## 結論狀態
- `SPARK_FUTURES`：**CONTRADICTION**（待營業員確認）。
- `LEGACY_QUOTE_T`：**SERVER_DENIED**（正確ID確認；T 盤 session 權限缺失）。
- `LEGACY_QUOTE_TPLUS1`：**SERVER_CONFIRMED**。

## 給客服/營業員的證據包
見 `YUANTA_SUPPORT_EVIDENCE_PACKET.md`（無 PII）。

# Yuanta Pending Validations（待驗證清單）

## Pending: Legacy Quote T session retest
- **When**：正常 T session 時段（台灣時間 08:45–13:45，交易日）。
- **Command**：`powershell -ExecutionPolicy Bypass -File scripts\yuanta_futures_auth.ps1`（已只提示密碼）。
- **Expected**：`Status=2`（T 盤其實有權限，凌晨只是盤外 LinkFail）或 `Msg[0]=3`（T 盤真的無權限）。
- **不得**：現在凌晨/盤外再亂測；不得猜分支代碼。

## Pending: SPARK Futures 0112
- 需營業員確認期貨帳號的 SPARK API Futures 權限。
- 見 `YUANTA_SUPPORT_EVIDENCE_PACKET.md`（無 PII）。

## Pending: OSE Micro（JNU）行情路徑
- SPARK StkCode / Legacy quote symbol / Trading order code 全 UNVERIFIED。
- 待 SPARK Futures 權限開通後，用 runtime MarketNo+StkCode 取得。

## 注意
以上皆為 **DEFERRED_EXTERNAL_VALIDATION**，不是 MARKET_AI_HUB core blocker。

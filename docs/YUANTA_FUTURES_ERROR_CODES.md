# Yuanta Futures COM Error Codes（只寫已驗證）

> 期貨 COM 錯誤碼**不沿用** Spark（0000/0001/0102/0112）。

## 已驗證

| code / 來源 | 意義 | 驗證方式 |
|---|---|---|
| `AddMktReg` return `0` | 行情註冊成功 | 官方 sample `YuantaQuoteAPI Sample.py` |
| `AddMktReg` return 非 0 | 行情註冊失敗 | 官方 sample |

## 未驗證（UNKNOWN，不猜）

- `OnMktStatusChange` 的 `Status` / `Msg` 具體數值語義 → 需真實 login 後實測。
- `OnRegError` 的 `ErrCode` → 需實測。

## 原則
- 未知 code → 標 `UNKNOWN`，不得猜。
- 登入成功與否：以 `OnMktStatusChange` 事件的實際狀態為準，
  **不以 `SetMktLogon` return 值當成功**（return 只代表呼叫 accepted）。

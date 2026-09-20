# Yuanta Futures Trading API — Future（未來研究導航）

> **CURRENT STATUS = NOT IMPLEMENTED / PROHIBITED_IN_PHASE2。**

## 官方下載（期貨 API 頁）
- 交易 API 元件及說明文件：**version 1.6.1.3**
- C# sample、Python trading sample
- 要求：「API 交易服務風險預告暨申請使用聲明書」+ 申請核准。

## 本棒只允許
- static inventory、documentation review、version/hash、architecture、
  official download source、required permission、certificate prerequisite、
  future integration design notes。

## 官方登入/帳戶發現架構（未來 metadata flow，不猜）
- **`SetFutOrdConnection` 使用「歸戶 ID」**（不是 branch code；branch 不是 login 欄位）。
- 登入成功後，事件 **`OnLogonS` 的 `AccList`** 才回傳：
  - `Branch`
  - `Account`
  - `SubAccount`
- 因此：未來需要 authoritative branch/account mapping 時，**由這個安全 metadata flow 取得**，
  不是猜、不是 brute-force。

## 本棒禁止
- register trading OCX、登入 trading API、查帳務、SendOrder、Cancel、Modify、任何 order。
- instantiate trading control（FUTURE_RESEARCH_ONLY）。

## 未來自動交易架構（只畫設計，不實作）
```
Strategy Research
  ↓
Human Approval Gate
  ↓
Execution Risk Engine
  ↓
Broker Adapter
  ↓
Yuanta Futures Trading API
```

## 未來一定要做（pre-trade risk / safety）
- pre-trade risk
- max position
- max daily loss
- price band
- duplicate order prevention
- kill switch
- session/calendar guard
- reconnect reconciliation
- order-state machine
- fill reconciliation
- manual emergency stop

以上全部 **NOT IMPLEMENTED / PROHIBITED_IN_PHASE2**。

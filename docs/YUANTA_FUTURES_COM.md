# Yuanta Futures Quote COM API（期貨行情）

## 元件
- **`YuantaQuote_v2.1.2.9.ocx`**（ActiveX control，非一般 COM DLL）
- ProgID：`YUANTAQUOTE.YuantaQuoteCtrl.1`
- CLSID：`{8E7FB42A-1137-467E-98C6-830C9B02EA82}`
- TypeLib：`{350F911B-4F62-42AF-BCD5-83B431A4BBDF}`
- 路徑：`C:\Yuanta\QAPI\YuantaQuote_v2.1.2.9.ocx`
- ThreadingModel：**Apartment（STA）**
- 架構：**x86（32-bit，WOW64 註冊）**

## 重要限制
- 32-bit OCX → **不能**在 64-bit Python 直接使用。
- 需**隔離 32-bit Python sidecar**（`.venv-yuanta-futures-x86`）。
- 是 ActiveX control → 需 **window handle + STA message pump**（官方 sample 用 wx）。

## Python 環境（sidecar）
- 32-bit Python 3.11（`Python311-32`）+ `comtypes` + `pywin32`。
- 主 MARKET_AI_HUB 維持 x64 不變。

## 官方 sample 載入方式
```python
from ctypes import byref, POINTER, windll
from comtypes import IUnknown, GUID
from comtypes.client import GetBestInterface, GetEvents
atl = windll.atl
# 建立 ActiveX control 在 window handle 上
atl.AtlAxCreateControlEx("YUANTAQUOTE.YuantaQuoteCtrl.1", hwnd, None,
                         byref(Iwindow), byref(Icontrol), byref(GUID()), Ievent)
quote = GetBestInterface(Icontrol)
events = GetEvents(quote, handler)
```

## 登入（`SetMktLogon`）
```python
# 第一參數是「登入ID」（官方 sample label：登入ID；身份證ID/登入ID），不是期貨帳號！
# T 盤 port 80/443, T+1 盤 port 82/442；reqType=1 T盤, reqType=2 T+1盤
quote.SetMktLogon(login_id, password, 'apiquote.yuantafutures.com.tw', '80', 1, 0)
quote.SetMktLogon(login_id, password, 'apiquote.yuantafutures.com.tw', '82', 2, 0)
```

⚠️ **login_id ≠ futures_account**：`legacy_login_id`（登入ID）與 `futures_account`（FF 帳號）
永久分離。登入ID 存 WinCred target `MARKET_AI_HUB/YUANTA/LEGACY_LOGIN_ID`
（`scripts/setup_yuanta_legacy_login_id.ps1`），不落 source/config/docs/log。

## 登入結果語義（官方 TLinkStatus，2026-09-19 修正）
| Status（TLinkStatus） | 意義 |
|---|---|
| -2 | **LinkFail（網路連線失敗）** ← 不是 permission denied |
| -1 | LinkBroken |
| 0 | Idle |
| 1 | Connected（連線成功，等待登入） |
| 2 | **LogonOK（登入成功）** |

**Msg[0]=='3' 才代表「無權限」（PERMISSION_DENIED）。**

先前把 status=-2 當「無登入權」是**錯誤解讀**。正確：先看 Status（link 狀態），再看 Msg[0]（結果碼）。

## T / T+1 endpoint（官方 C# sample）
| 盤別 | reqType | ports |
|---|---|---|
| T 盤 | 1 | 80 / 443 |
| T+1 盤 | 2 | 82 / 442 |

- `SetMktLogon` **沒有 branch-code login parameter**（禁止猜分支代碼）。
- T 真實 probe 只在正常交易日 T session 時段執行（session-aware）。
- TCP reachable ≠ authentication success。

## 行情註冊
```python
ret = quote.AddMktReg(symbol, mode, ret_type, 0)   # ret == 0 = 成功
quote.DelMktReg(symbol, ret_type)                  # 取消註冊
```

## 事件
| handler | 用途 |
|---|---|
| `OnMktStatusChange(this, Status, Msg, ReqType)` | 市場/登入狀態（**登入結果在此確認**） |
| `OnGetMktQuote(this, symbol, DisClosure, Duration, ReqType)` | 報價 |
| `OnGetMktData(this, PriType, symbol, Qty, Pri, ReqType)` | 成交 |
| `OnRegError(this, symbol, updmode, ErrCode, ReqType)` | 註冊錯誤 |
| `OnGetTickData` / `OnGetTickRangeData` / `OnGetTimePack` 等 | tick/其他 |

## 錯誤碼
見 `docs/YUANTA_FUTURES_ERROR_CODES.md`（**不沿用 Spark 0001/0102/0112**）。

## 禁止
- ❌ 用 Spark `YuantaSparkAPITrader` 登期貨帳號。
- ❌ 猜 OSE Micro symbol = TradingView/JPX code。
- ❌ 下單（本 API 只做 quote；order 屬 `YuantaOrderAPI`，永不實作）。

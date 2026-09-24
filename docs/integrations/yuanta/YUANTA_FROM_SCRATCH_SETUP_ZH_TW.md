# 元大 API 從零建置與重建手冊（繁體中文）

> 目的：讓新的工程師或任何 AI agent 不依賴聊天記憶，也能從零重建 MARKET_AI_HUB 的元大行情環境。
> 本文件同時區分「元大官方契約」與「MARKET_AI_HUB 2026-09-24 正式環境實測」。
> Machine-readable source：`config/yuanta_source_manifest.yaml`。

## 1. 三套 API 永久分離

### 1.1 SPARK API
元大官方 SPARK 為 .NET 8 API，支援 Windows/Linux/macOS，Python 透過 pythonnet 呼叫。
官方文件支援證券及期貨市場；帳號權限依帳號個別開通。

MARKET_AI_HUB：
- SPARK securities profile 登入 PROD，MsgCode=0001。
- 實測收到 TAIFEX、OSE、CME、CBOT、CBOE、NYBOT matching quote callback。
- 目前跨市場主要即時行情來源。
- SPARK securities quote success 不等於 SPARK futures-account entitlement。

### 1.2 元大期貨行情 API / Legacy YuantaQuote
獨立 32-bit ActiveX/COM 行情 API，不是 YuantaOrd。
目前作為國內 TAIFEX 備援來源。

2026-09-24 PROD 實測：
- T / T+1 均 Status=2 / LogonOK / code=0。
- TX / MTX / TMF / UNF T+1 均收到 OnGetMktData。
- canonical login：身分登入ID + 證券電子密碼（敏感值只存 WinCred）。
- canonical AddMktReg：`AddMktReg(base_symbol, 4, ReqType, 0)`。

### 1.3 元大期貨交易 API / YuantaOrd
與行情 API 分開安裝、分開申請。
本專案 live quote runtime 不得載入、不得呼叫、不得下單。

> 本專案不是「元大期貨槓桿全球贏家 Web API」，不得混淆。

## 2. 官方下載來源

### 2.1 SPARK
官方入口：
- https://www.yuanta.com.tw/file-repository/content/API/page/index.html
- https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/index.html

Windows Python：
- x64: https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_win-x64_Python.zip
- x86: https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_win-x86_Python.zip

C#：
- https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_CSharp.zip

UAT 測試憑證：
- https://ys.yuanta.com.tw/quartet/api/B110000005_TWCA.zip
- 憑證密碼等敏感/安控細節請依元大官方說明，不複製到 repo。

官方換版歷程：
- https://ys.yuanta.com.tw/quartet/api/YuantaApiHis.pdf

目前 repo pin：
- package version：`2.2026.0918.0`
- vendor root：`vendor/yuanta_spark/2.2026.0918.0/YuantaSparkAPI_win-x64_Python`

### 2.2 元大期貨 API
官方總下載頁：
- https://www.yuantafutures.com.tw/ytf/easywin/api/download.html

官方目前列示：
- 交易 API 元件及說明文件：1.6.1.3
- 國內行情 API 元件及說明文件：2.1.2.7

直接樣例：
- Python交易範例：https://www.yuantafutures.com.tw/ytf/easywin/download/YuantaOrdAPI_py.zip
- Python行情範例：https://www.yuantafutures.com.tw/ytf/easywin/download/YuantaQuoteAPI_py.zip
- 行情 C# 範例：https://www.yuantafutures.com.tw/ytf/easywin/download/API_Yuanta2.1.2.7.zip

元件 ZIP：
- 行情 API：https://www.yuantafutures.com.tw/ytf/easywin/download/行情API元件及說明文件.zip
- 交易 API：https://www.yuantafutures.com.tw/ytf/easywin/download/交易API元件及說明文件.zip
- 兩個 direct URL 已於 2026-09-24 用 HTTP HEAD 實測 200；仍以官方總下載頁作最新版 source of truth。

穩定做法：永遠先以官方下載頁為 source of truth，不把舊 ZIP URL 當永久版本鎖。

本機原始資料備份：
- `C:\Users\fishk\Documents\元大期貨API`
- `C:\Users\fishk\Documents\元大憑證`

## 3. API 權限規則

SPARK 官方 FAQ：
- API 權限依帳號開通。
- 證券帳號與期貨帳號個別開通。
- UAT 需由營業員處理固定 IP 防火牆。

元大期貨官方下載頁：
- 交易與行情 API 皆需先申請核准。

系統規則：
- provider 可用 → 保存 live lineage。
- provider 不可用 → 保存 NOT_AVAILABLE / entitlement truth。
- 外部 entitlement 不阻塞核心模型架構。


## 4. SPARK Windows 從零安裝

### 4.1 系統需求
依官方文件：
1. 安裝 .NET SDK 8.0。
2. Python 建議 3.8+。
3. 安裝 pythonnet：`pip install pythonnet`。
4. 使用 x64 Python 時下載 x64 SPARK package。
5. package 內需要的 DLL 必須完整保留。

本專案使用：
- Python 3.12 x64
- pythonnet
- .NET 8
- `.venv`

建議檢查：
- `dotnet --info`
- `python --version`
- `python -m market_ai_hub.integrations.yuanta.spark_runtime_probe`

只有 interop READY 才進 login。

### 4.2 元件載入規則
1. `pythonnet.load("coreclr")`
2. 將 package root 放入 Python path / DLL search path。
3. `clr.AddReference("YuantaSparkAPI")`
4. 建立 `YuantaSparkAPITrader()`
5. 強引用 OnResponse delegate，避免 pythonnet GC 回收 callback。
6. `Open(PROD)`
7. `Login(account,password)`
8. 真正 login 結果只認 `OnResponse -> LoginStatus.MsgCode`。

`Login()` 回傳 True 只代表呼叫被接受，不代表 server 驗證完成。

## 5. SPARK 憑證安裝

### 5.1 UAT
官方測試憑證 ZIP：
https://ys.yuanta.com.tw/quartet/api/B110000005_TWCA.zip

Windows 依官方憑證匯入精靈安裝至目前使用者。
UAT 另需營業員開固定 IP 防火牆。

### 5.2 PROD
官方說明：
- 正式憑證須先在元大網站申請。
- 將正式憑證匯入 Windows 目前使用者憑證 store。
- Windows 可由 Chrome → 設定 → 隱私權和安全性 → 安全性 → 管理 Windows 憑證 → 匯入。

元大期貨憑證中心：
- https://www.yuantafutures.com.tw/certificate
- https://www.yuantafutures.com.tw/newcomer_03

安全規則：
- private key / PFX / 憑證密碼不得進 Git、log、chat。
- Windows SPARK `Login(Account,Pass)` 不由程式傳 PFX 路徑。
- Linux/macOS 才依官方 Login contract 傳 PFX path/password。
- repo 檢查工具：`scripts/check_yuanta_certificate.ps1`，只回報是否存在/有效，不輸出 subject、thumbprint 或 private key。

## 6. MARKET_AI_HUB Windows Credential Manager

這是登入帳密安全保存機制，與正式交易憑證不同。

canonical targets：
- `MARKET_AI_HUB/YUANTA/SECURITIES`
- `MARKET_AI_HUB/YUANTA/FUTURES`
- `MARKET_AI_HUB/YUANTA/LEGACY_LOGIN_ID`

設定：
- `python scripts/setup_yuanta_credentials.py --profile securities`
- `python scripts/setup_yuanta_credentials.py --profile legacy_login_id`
- 選擇性：`python scripts/setup_yuanta_credentials.py --profile futures`

查看：
- `python scripts/setup_yuanta_credentials.py --status`

規則：
- account/login ID 只在本機 terminal 輸入。
- password 使用 getpass。
- 不以 command line argument 傳 password。
- 不以 env var 長期保存。
- 不在 chat、log、report、Git 中保存完整帳號/登入ID/password。
- pywin32 可能把 secret 讀成 UTF-16LE bytes；必須經 `normalize_credential_secret()`。

### Legacy Quote canonical credential
2026-09-24 PROD 實測成功：
- username：`LEGACY_LOGIN_ID` profile（身分登入ID，只在 WinCred）
- password：`securities` profile 電子密碼

不得把期貨 FF account 當 `SetMktLogon` 第一參數。

## 7. Legacy Futures Quote x86 安裝

官方/本機流程：
1. 從元大期貨下載 `國內行情API元件及說明文件`。
2. 解壓後將 `QAPI` 放到 `C:\Yuanta\QAPI`。
3. 以系統管理員執行 `install_ytocx.bat`。
4. 出現 DLL RegisterServer success 才算 OCX 註冊成功。
5. Python wrapper 必須使用 32-bit Python/pywin32。

repo：
- `scripts/setup_yuanta_futures_x86.ps1`
- `scripts/check_yuanta_futures_com.ps1`

目前實測：
- ProgID: `YUANTAQUOTE.YuantaQuoteCtrl.1`
- x86 sidecar
- T / T+1 login OK

次級交叉參考：
https://itrader.com.tw/%E5%85%83%E5%A4%A7%E6%9C%9F%E8%B2%A8api%E9%96%8B%E7%99%BC%E5%89%8D%E6%BA%96%E5%82%99/

## 8. Legacy Quote 登入/訂閱契約

Login：
`SetMktLogon(login_id, password, host, port, ReqType, 0)`

成功：
- 必須收到 OnMktStatusChange。
- `Status=2 / LogonOK` 才算 server-verified。

T/T+1：
- ReqType=1：T
- ReqType=2：T+1

AddMktReg：
`AddMktReg(base_symbol, 4, ReqType, 0)`

規則：
- UpdateMode=4。
- SetMap=0。
- T+1 仍使用 base symbol。
- EasyWin `xxxPM` 是 UI/alias metadata，不是 Legacy canonical AddMktReg symbol。
- AddMktReg return=0 本身不算成功。
- 只有收到 `OnGetMktData` / `OnGetMktQuote` 才算 `LIVE_CALLBACK_VERIFIED`。


## 9. SPARK Quote Hub 正式操作

啟動：
- `scripts/start_yuanta_live_recorder.ps1`

狀態：
- `scripts/get_yuanta_live_status.ps1`

Agent 先讀：
- `data/live/yuanta/status.json`
- `data/live/yuanta/latest.json`

需要新商品：
- `scripts/request_yuanta_quote.ps1 -MarketNo <market> -Symbol <quote_code>`

Hub 在既有 SPARK connection 上追加訂閱。
agent 使用完成：
- 不 Logout
- 不 Close
- 不另開第二登入

只有 recorder process 或 Windows 結束時才斷線。

Windows Startup 已配置執行 start script；start script 有 single-instance PID gate。

## 10. 長期資料保存策略

優先保存公開網路難以完整重建的盤中資料：
- OSE Micro direct
- TAIFEX TX/MTX/TMF/UNF
- CME NQ/MNQ/ES/JY/GC/CL
- CBOT ZF/ZN
- CBOE VX
- NYBOT DXY futures
- 台股交易時段 TAIEX / 2330 context
- 近月＋次近月
- 成交價/量、累計量、bid/ask等 callback可取得欄位
- source time-of-day
- received_at UTC
- contract/roll identity

主格式：
- `data/live/yuanta/parquet/YYYY-MM-DD/*.parquet`

不重複大量保存：
- 可由 Yahoo/FRED/官方歷史資料穩定重抓的日線/宏觀資料。

`data/live/` 已 gitignore。

## 11. 從零重建驗收順序

任何新 agent 必須照順序：

1. `scripts/agent_bootstrap.ps1`
2. 讀 `AGENTS.md`
3. 讀 `docs/development/AGENT_HANDOFF.md`
4. 讀本文件
5. 讀 `config/yuanta_source_manifest.yaml`
6. 讀 `config/yuanta_live_factor_matrix.yaml`
7. 確認 .NET8 / pythonnet / SPARK package
8. `scripts/check_yuanta_certificate.ps1`
9. `python scripts/setup_yuanta_credentials.py --status`
10. `python -m market_ai_hub.integrations.yuanta.spark_runtime_probe`
11. `scripts/start_yuanta_live_recorder.ps1`
12. 確認 status=RUNNING、login_msg_code=0001、heartbeat持續更新
13. 檢查 latest.json 有 matching market+instrument callback
14. 才允許模型使用 live factor

禁止：
- 為了 quote 載入 YuantaOrd。
- 把 Subscribe return=True 當 live success。
- 把 futures proxy 冒充 cash index。
- 把 quote code 冒充 order code。
- 把測試當日 contract hardcode 成永久碼。
- 因某一 provider unavailable 就停止核心系統。

## 12. 參考來源

官方：
- SPARK入口：https://www.yuanta.com.tw/file-repository/content/API/page/index.html
- SPARK文件：https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/index.html
- SPARK Python Windows：https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/2.Python%E8%A8%AD%E5%AE%9A/Windows%E3%80%81Mac%E7%B3%BB%E7%B5%B1/index.html
- SPARK Login：https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%9F%BA%E7%A4%8E/%E7%99%BB%E5%85%A5/index.html
- SPARK SubscribeWatchlistAll：https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E8%A1%8C%E6%83%85/%E8%A1%8C%E6%83%85%E5%A0%B1%E5%83%B9%E8%A1%A8%E8%A8%82%E9%96%B1/index.html
- SPARK市場列舉：https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%9F%BA%E7%A4%8E/%E5%88%97%E8%88%89%E7%89%A9%E4%BB%B6/index.html
- 元大期貨API下載：https://www.yuantafutures.com.tw/ytf/easywin/api/download.html
- 元大期貨憑證中心：https://www.yuantafutures.com.tw/certificate
- 元大期貨客服：https://www.yuantafutures.com.tw/ContectUs

次級（只作交叉驗證，不覆蓋官方/實測）：
- iTrader：https://itrader.com.tw/%E5%85%83%E5%A4%A7%E6%9C%9F%E8%B2%A8api%E9%96%8B%E7%99%BC%E5%89%8D%E6%BA%96%E5%82%99/
- iThome：https://ithelp.ithome.com.tw/articles/10222522

## 13. 當前正式驗證狀態

2026-09-24：
- full suite: 1691 passed / 20 deselected / 144 warnings
- SPARK securities PROD login: MsgCode=0001
- SPARK matching callbacks: TAIFEX/OSE/CME/CBOT/CBOE/NYBOT verified
- Legacy T/T+1 login: verified
- Legacy TX/MTX/TMF/UNF T+1 callbacks: verified
- Persistent Quote Hub: running
- Same-PID dynamic subscription: verified
- Trading/order/account query: disabled

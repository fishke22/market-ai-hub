# 元大 API 整合 — 交接包（更新 2026-10-06）

## 目標
取得大阪微型日經（JNU）期貨的成交/沖銷明細，供模型分析賺賠習性。

## ✅ 已驗證成功：期貨交易 API（YTFutOrdAP）

### 登入（關鍵！）
- COM 元件：`Yuanta.YuantaOrdCtrl.1`（32-bit OCX，已註冊）
- **執行環境：`D:\MARKET_AI_HUB\.venv-yuanta-futures-x86\Scripts\python.exe`（32-bit，必要）**
- 登入函式：`SetFutOrdConnection(ID, Pass, "api.yuantafutures.com.tw", "443")`
- **登入 ID：存於 Windows Credential Manager target `MARKET_AI_HUB/YUANTA/LEGACY_LOGIN_ID`（歸戶 ID，不是 branch/帳號；內容不寫入任何文件）**
- 密碼：與證券登入同一組（Windows Credential Manager 讀，不寫死）
- 成功事件：`OnLogonS(狀態=2, AccList="2-<branch>-<account>--<姓名>", 憑證序號="SN=<序號>")`
- 帳號解析：AccList 格式 `市場別-Branch-Account-SubAccount-姓名`；市場別 2=期貨 → f[1]=bhno、f[2]=acno、f[3]=suba。程式以 `account_params()` 由 AccList 動態組裝，源碼不含實際帳號。

### 查詢（唯讀，全部實測成功）
| 函式 | 用途 | 事件（注意參數數） |
|------|------|------------------|
| `RfDealQuery(bhno, acno, suba, "*")` | 國外期貨成交回報 | `OnRfDealQuery(arg0=筆數, arg1="\|"分隔的逐筆成交)`；成交欄位：SYMB/SCNAM/A_PRC(成交價)/DEAL_QTY/O_DATE/D_TIME/BUYS/O_KIND/ORDER_NO/EXCHANGE |
| `RfReportQuery(bhno, acno, suba, "0", "0", "*")` | 國外期貨委託回報 | `OnRfReportQuery(arg0=筆數, arg1=逐筆委託)` |
| `UserDefinsFunc("Func=RA004\|bhno=<branch>\|acno=<account>\|suba=\|FC=N", "RA004")` | 外期未平倉明細 | `OnUserDefinsFuncResult(RowCount, Results, WorkID)`；回傳 `retc=00000\|...\|count=N\|TRDDT/EXH/COMNO(JNU2612)/PS/QTY/MKTPRE1(市價)/TRDPRC1(成交價)/PRTLOS1(未平倉損益)/ORDNO/CURRENCY` |

### 坑（以後會踩的）
1. `win32cred.CredRead` 的密碼是 **bytes**，要 `decode("utf-16-le"/"utf-8"/"mbcs")` 再傳。
2. 成交/委託回報事件是 **2 參數**（筆數, 資料），不要只抓 arg0。
3. 回傳中文是 **Big5 經 Latin-1 混亂**，要 `str(s).encode("latin-1").decode("big5")`。
4. COM 需 **STA + 隱藏視窗 + `AtlAxCreateControlEx` + `PumpWaitingMessages`**（模式見 `src/.../yuanta/futures_com.py`）。

## ⚠️ Spark API（證券）實測：限證券
- `GetHisRealizedGainLoss(證券帳號, "2026/07/06", "2026/10/06")` → 9 筆，**全是證券**（0050/2356/3231/2344/3702），**JNU 期貨 0 筆**（文件註「限證券使用」）。
- 結論：證券 Spark 帳號查不到期貨；期貨資料要走上面的**期貨交易 API**。

## 憑證位置（Windows Credential Manager）
- `MARKET_AI_HUB/YUANTA/SECURITIES`（證券登入；fallback `QROS/Yuanta/SecuritiesReadonly`）
- `QROS/Yuanta/FuturesTradingQueryReadonly`（期貨交易查詢唯讀）
- `QROS/Yuanta/FuturesReadonly`
- `MARKET_AI_HUB/YUANTA/LEGACY_LOGIN_ID`（歸戶登入 ID；內容不寫入文件，程式執行時從 WinCred 讀）

## 程式位置
- 期貨交易 API 測試：`D:\MARKET_AI_HUB\scripts\futures_trade_api_test.py`（用 x86 venv 跑）
- Spark 帳務測試：`D:\MARKET_AI_HUB\scripts\spark_realized_reversal_test.py`（用 .venv 跑）

## 已下載的沖銷明細檔案（2026-10-06 確認）
- **檔案**：`C:\Users\fishk\Downloads\平倉損益查詢結果_20260610223405.xls`（239.5 KB，**真 BIFF 二進位 .xls**）
- **讀取**：需 `xlrd`（已裝到 `D:\MARKET_AI_HUB\.venv`，`uv pip install xlrd`）+ pandas（engine='xlrd'）
- **結構**：1 個工作表 [Sheet]，**1369 筆 × 11 欄**
  - 委託書號 / 商品名稱 / 買賣別 / 成交日期(yyyy/MM/dd) / 成交價格 / 成交口數(「(平)」=平倉註記) / **平倉損益** / 幣別(JPY) / 手續費 / 稅 / **淨損益**(=平倉損益-手續費)
  - 商品：大阪微日經2609(872 筆)、大阪微日經2612(493 筆)、大阪小日經2609(4 筆)
  - 日期：2026/07/09 ~ 2026/10/06（JNU 沖銷明細，JPY 計價）
- 讀取範例：
  ```python
  import pandas as pd
  df = pd.read_excel(r'C:\Users\fishk\Downloads\平倉損益查詢結果_20260610223405.xls', engine='xlrd')
  ```

## 交易行為分析（2026-10-06）
- **完整報告**：`D:\MARKET_AI_HUB\docs\JNU_TRADING_BEHAVIOR_REPORT.md`
- **分析腳本**：`D:\MARKET_AI_HUB\scripts\pnl_analysis.py`（條件期望值）、`pnl_deep_analysis.py`（每日/連敗/週別/大虧損）
- **關鍵結論**：
  - 569 筆平倉、勝率 83%、總損益 +1,155,950 JPY、盈虧比 0.31（賺小賠大）
  - 做空強於做多；口數 ≤5 賺錢、≥4（尤其 6/7/20/40）賠錢（重倉=主虧損源）
  - 2612 合約主力獲利（+1,281,750）、2609 小賠
  - **賠後連動**：前一筆賠→下一筆勝率掉到 47%、期望值 -4,620（報復性交易）
  - 4 筆大虧損（-946,150）吃掉絕大部分獲利
  - 此檔無成交時間欄 → 時段分析需含時間的報表
  - **趨勢對齊**（Yahoo `NIY=F`，與 JNU 同指數點位）：上漲日 +1,095,550（主力賺）、盤整日 -252,500（最大虧損情境）、下跌日 +105,100

## 待解（已探測確認）
1. **歷史（7/6～今）期貨沖銷明細：兩套 API 都拉不到**（2026-10-06 探測確認）：
   - 交易API `RfDealQuery`/`RfReportQuery` = 當日（O_DATE=20261006）。
   - `UserDefinsFunc` 探測 FA001~FA050、RA001~RA030：成功代碼只有 RA002（財務）、RA003（部位狀況）、RA004（外期未平倉明細），皆「當下狀態」；FA 系列全部回 `Invalid Param tag: sdate`（不接受日期）。
   - Spark API `GetHisRealizedGainLoss` 有日期範圍但「限證券」（實測 9 筆全 TWSE，JNU 0 筆）。
   - EasyWin 的 `CX_REPORT.DLL` 是內部報表元件，非公開 API。
   - **可行路徑**：(a) 元大官網/iTRADER 匯出歷史沖銷明細 CSV；(b) 從今天起每日用 `RfDealQuery` 自動累積成交明細。
2. 成交回報的 `O_KIND`（新倉/平倉）欄位解碼後可做沖銷配對（FIFO）。

## 官方範例資料夾（已全讀，2026-10-06）
- `Downloads\YuantaQuoteAPI_py\YuantaQuoteAPI Sample.py`（19KB）：行情 API Python 範例（wxPython + comtypes，OCX `YuantaQuote`）。
- `Downloads\YuantaOrdAPI_py\YuantaOrdAPI Sample.py`（30KB）：下單 API Python 範例。
  - **UserDefinsFunc 官方預設代碼 = `FA022`**（`Func=FA022|bhno=|acno=|suba=`）。
  - 事件簽名（實測與文件一致）：`OnRfDealQuery(this, RowCount, Results)`、`OnRfReportQuery(this, RowCount, Results)`、`OnUserDefinsFuncResult(this, RowCount, Results, WorkID)`。
  - 查詢函式：`RfReportQuery(bhno,acno,suba,stus,cflg,exch)`、`ReportQuery("F",...)`、`RfDealQuery(bhno,acno,suba,'*')`、`DealQuery("F",...)`。
  - 下單 offset 選項：`0-新倉, 1-平倉, 2-當沖, 空白-自動`（→「沖銷」在期貨下單語境 = `1-平倉`）。
- `Downloads\交易APIC＃範例\交易API C# 範例\Form1.cs`（21KB）：C# 範例，事件簽名確認（OnRfDealQuery(int RowCount, string Results) 等），UserDefinsFunc 是自由輸入框。
- `Downloads\API_Yuanta2.1.2.7`：**舊版（2017）行情 API 2.1.2.7**（QuoteTest C# 專案 + YuantaQuote_v2.1.2.7.ocx）——歷史版本，僅供參考。

## UserDefinsFunc 功能代碼的「必填參數」表（探測得知）
| 代碼 | 必填參數 | 備註 |
|------|---------|------|
| FA001 | kind | 未平倉合計（0683） |
| FA002 | kind | 未平倉明細（0682） |
| FA003 | type | 財務（0680） |
| **FA004** | **clear_date** | ⚠️ 接受參數但實測不回傳資料（可能是歷史平倉明細，需更多參數） |
| **FA005** | **start_date** | ⚠️ 同上 |
| FA006 | （未知代碼） | Unknow TaskName |
| **FA007~FA021** | **from** | ⚠️ 接受 from 但實測不回傳 |
| FA009 | kind | 未平倉合計（0681） |
| FA022 | （無） | 官方範例預設代碼；實測回 `VREC=0001|EMSG=成功(0)` 但 0 筆 |
| FA023/FA024 | kind | 回 TOTAL_OFF_POS 欄位（未平倉合計類） |
| FA025 | （無） | 實測回 `retc=00001` 成功但 count=0 |
| RA002 | （無） | 財務查詢 ✅（權益/保證金/JPY 損益） |
| RA003 | （無） | 部位狀況 ✅（JNU 留倉/了結/損益） |
| RA004 | FC | 外期未平倉明細 ✅（JNU 未平倉 4 筆） |

> 日期參數名是 `clear_date` / `start_date` / `from`（**不是** sdate/edate）。但帶上日期後實測**不回傳資料**（25 秒無回應）——歷史查詢可能需額外參數或權限，暫擱置。

## 探測腳本
- `D:\MARKET_AI_HUB\scripts\futures_userdef_probe.py`（v1：帶 kind 參數，多數回 Invalid Param tag: kind）
- `D:\MARKET_AI_HUB\scripts\futures_userdef_probe2.py`（v2：不帶 kind、試 sdate/edate → FA 系列不接受日期）
- `D:\MARKET_AI_HUB\scripts\futures_userdef_probe3.py`（v3：最小參數 → 得知各代碼的必填參數名）
- `D:\MARKET_AI_HUB\scripts\futures_userdef_probe4.py`／`probe5.py`（v4/v5：clear_date/start_date/from → 25 秒無回應）

## 已安裝技能（2026-10-06）
- `anthropics/skills@xlsx`（177.8K installs）→ `C:\Users\fishk\.agents\skills\xlsx`（openpyxl/pandas/markitdown）——讀取元大匯出的沖銷明細 Excel 用。

## 唯讀界線（鐵律）
- 只做查詢；**絕不呼叫 `SendOrderF` / `RfSendOrder`**（下單）。
- 密碼一律從 Windows Credential Manager 讀，不寫死、不輸出。

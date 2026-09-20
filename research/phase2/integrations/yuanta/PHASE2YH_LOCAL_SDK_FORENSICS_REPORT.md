# PHASE 2Y-H — Yuanta Local SDK Forensics Report

- Gate：**PHASE2YH_PASS**
- 前置：PHASE2VA_PASS
- 性質：**只讀鑑識**（無真實登入 / 無下單 / 無帳戶查詢 / 無訂閱 / 未修改 SDK / 未 GitHub push）
- 產物：`YUANTA_LOCAL_SDK_INVENTORY.json`（227 檔案 + SHA256）

---

## 1. Documents 資料夾裡到底有什麼（219 檔案）
`C:\Users\fishk\Documents\元大期貨API`（已解壓）：
| 分類 | 內容 | 關鍵元件 |
|---|---|---|
| A. SPARK / OneAPI | （無；SPARK 在 Downloads\元大證券元件） | — |
| B. Legacy Futures Quote | `QuoteAPISDK\行情API元件及說明文件` + `API_Yuanta2.1.2.7` | `YuantaQuote_v2.1.2.9.ocx`（153KB, 2022-11-29）、`YuantaQuote_v2.1.2.7.ocx`（152KB, 2020-09-27） |
| C. Legacy Futures Trading | `OrdAPISDK\交易API元件及說明文件` | `YuantaOrd.ocx`（416KB, 32-bit）、`YuantaOrd64.ocx`（506KB, 64-bit）、`YuantaCAPIDLL.dll/64.dll` |
| D. 其他工具 | WebView2 runtime、CA 簽章 adapter | `Microsoft.WebView2...x64.cab`（297MB）、`YuantaCAPIServiSignAdapterSetup.exe` |
| 文件 | PDF/docx/txt | `元大行情API.pdf`（495KB）、`元大BToCAPI格式.pdf`（795KB）、`元大API交易PYTHON注意事項.docx`、`使用說明.txt`×2 |
| Sample | Python + C# | `YuantaQuoteAPI Sample.py`、`YuantaOrdAPI Sample.py`、`交易API C# 範例` |

## 2. Downloads vs Documents 哪個版本新
- `Downloads\元大期貨元件`：3 個 zip（`API_Yuanta2.1.2.7.zip` 5890836B、`YuantaQuoteAPI_py.zip` 4804B、`行情API元件及說明文件.zip` 7093101B）。
- `Documents\元大期貨API`：同一批 zip **已解壓**（含 `YuantaQuote_v2.1.2.9.ocx`）。
- **版本結論：SAME**（Downloads zip 與 Documents 解壓內容同源）。
- Quote OCX：**v2.1.2.9（2022-11-29）比 v2.1.2.7（2020-09-27）新**；v2.1.2.9 是目前最新。

## 3. Quote API 是否只支援國內
**DOMESTIC_ONLY**（證據）：
- 官方 `元大行情API.pdf` 版本歷史：`1.0.0.1 國內證券報價 + 期貨行情顯示`、`2.0.1.1 證券報價顯示+新增12項`。
- 全本機 Quote SDK 搜尋 `海外/國外/外期/海期/international/overseas/OSE/JPX/Nikkei` → **0 命中**。
- 對照：Trading API `元大BToCAPI格式.pdf` 1.6.1.1 有「支援國外(外網)期貨下單 Taione」→ 海外期貨是**交易 API** 範疇，非行情 API。

## 4. EasyWin symbol table 是否找到
**未找到實際對照表**。但**語義 VERIFIED**：官方 `元大行情API.pdf` 明寫 `AddMktReg` 期貨類 Symbol = **同 EASYWIN 期貨報價代碼**。
→ `docs/YUANTA_EASYWIN_SYMBOL_MAPPING.md`（實際碼 UNRESOLVED）。

## 5. JNU legacy quote symbol 是否找到
**未找到**。Legacy Quote SDK 全無 JNU/JNI/JNM/OSE/Nikkei。OSE 代碼只存在於 **SPARK** 的 FunctionList（非 Legacy Quote）。

## 6. 7xxx 規則是否找到
**本機 SDK 未找到**（`7xxx`/`報價代碼變更規則` 0 命中）。該規則在 `YuantaOneHis.pdf`（2021/06），屬 legacy OneAPI 歷史命名空間。
→ `docs/YUANTA_FUTURES_QUOTE_CODE_RULES.md`。

## 7. OSE SPARK StkCode confirmation（永久保存，防再誤判）
- 檔案：`FunctionList.xlsx` 股票代碼總表，SHA256 `39b0f2244981258399b840e9d4c9e9b3cc85d2425fdc14f4058f328bb8fd4ea5`（3.4MB，2026-09-17）。
- 欄位：`市場別 | 市場代碼 | 商品代碼 | 商品名稱 | 下單代碼`。
- OSE Micro：市場別=OSE，市場代碼=207，商品代碼=`JNU2609`/`JNU2612`/`JNU2703`…，下單代碼=`JNU`。
- 已寫入 `config/yuanta_product_codes.yaml`（含 SHA256 + verified_at）。

## 8. 0112 是否找到額外解釋
- 本機 Legacy SDK **無 0112**（0112 是 SPARK MsgCode，非 Legacy）。
- Legacy Quote 對應「無權限」= `Msg[0]='3'`；Legacy Trading 對應 = `-102 lsInvalidLogonApiNo 無API權限`。
- 無額外 0112 說明可提（需 SPARK 文件，不在本棒 scope）。**UNRESOLVED**（SPARK 0112 語義已在先前 phase 記錄）。

## 9. Futures account format evidence
Legacy Trading（`元大BToCAPI格式.pdf`）：
- `SetFutOrdConnection(ID, Pass, IP, Port)` — 用 **元大歸戶 ID + 歸戶密碼**（非期貨帳號）。
- `OnLogonS` 回傳 `AccList = 市場別-Branch-Account-SubAccount-姓名`（例 `2-F00-9808900-0001-路人乙`）。
- 下單欄位：`BranchID`(分公司代碼, 3碼 ex F002) + `AcNo`(帳號 7碼) + `SubAcNo`(子帳號 4碼)。
- **只保存格式規則，未保存任何真實帳號。**

## 10. Quote/Trading 是否互相依賴
**INDEPENDENT_BY_DESIGN**（證據）：
- 不同 Domain：Quote=`apiquote.yuantafutures.com.tw`，Trading=`api.yuantafutures.com.tw`。
- 不同 OCX/ProgID：Quote=`YUANTAQUOTE.YuantaQuoteCtrl.1`，Trading=`Yuanta.YuantaOrdCtrl.1/.64`。
- 不同 login 方法：`SetMktLogon`（行情）vs `SetFutOrdConnection`（交易）。
- 官方 `使用說明.txt`：行情 API 是**獨立申請**（「一般的API申請為交易API…加申請行情API」）。
- （`QuoteTest` C# 範例雖 reference `Interop.YuantaOrderAPI.dll`，但那是範例自身同時演示行情+下單，非行情元件依賴交易元件。）

## 11. Quote login / status contract（VERIFIED）
Legacy Quote（`元大行情API.pdf` + `異動說明.docx`）：
- `SetMktLogon(User, pass, IP, PORT[, reqType, setMap])` — **User = 身份證ID**（非 FF 期貨帳號）。
- `reqType=1`=T盤、`reqType=2`=T+1盤（session label）。
- TLinkStatus：`-2 lsLinkFail`、`-1 lsLinkBroken`、`0 lsIdle`、`1 lsConnected`、`2 lsLogonOK`。
- `OnMktStatusChange` 的 `Msg[0]`：`'0'=Success`、`'3'=無權限`、`'6'=密碼錯誤`、`'E'=無此帳號`…。

## 12. Certificate requirement
| API | 判定 | 證據 |
|---|---|---|
| Legacy Quote | **NOT_REQUIRED_BY_DOC** | `SetMktLogon(ID, pass, IP, PORT)` 無憑證參數；`Msg[0]='I'=無客戶憑證序號資料` 僅回傳狀態 |
| Legacy Trading | **REQUIRED** | `TLinkStatus 4=lsCAError 憑證錯誤`；`OnLogonS` 回傳 `Casq`(憑證序號)/`Cast`(憑證狀態)；SDK 附 `YuantaCAPIServiSignAdapterSetup.exe`（CA 簽章 adapter） |
| SPARK Windows | **REQUIRED**（CA 簽章 adapter） | 同 `YuantaCAPIServiSignAdapterSetup.exe`（SPARK 證券已驗證 `MsgCode=0001` 需 CA） |

## 13. Trading API bitness / version
- OCX：`YuantaOrd.ocx`（32-bit, 2014-06-11）+ `YuantaOrd64.ocx`（64-bit, 2014-06-11）。
- ProgID：32-bit=`Yuanta.YuantaOrdCtrl.1`，64-bit=`Yuanta.YuantaOrdCtrl.64`（`元大API交易PYTHON注意事項.docx` VERIFIED）。
- 版本：`元大BToCAPI格式.pdf` 最後 `1.6.1.3`（修正 bug）。
- 環境：Python 3.9 + wxPython 4.1.1 + comtypes 1.1.11（官方範例）；bitness 必須與 OCX 一致。
- 未 instantiate Trading OCX（禁止）。

## 14. 哪些文件應進 GitHub（原創摘要/manifest）
- `YUANTA_LOCAL_SDK_INVENTORY.json`（hash/version manifest）。
- `docs/YUANTA_EASYWIN_SYMBOL_MAPPING.md`、`docs/YUANTA_FUTURES_QUOTE_CODE_RULES.md`、`docs/YUANTA_ONEAPI_VERSION_CAPABILITIES.md`。
- `PHASE2YH_LOCAL_SDK_FORENSICS_REPORT.md`。
- 更新 `config/yuanta_product_codes.yaml`（含 FunctionList SHA256）。

## 15. 哪些 binary/doc 不得發布
- 所有 `Documents\元大期貨API` + `Downloads\元大*元件` 的 DLL/OCX/EXE/CAB/PDF/docx/xlsx（proprietary）。
- `YuantaQuote_v2.1.2.9.ocx`、`YuantaOrd.ocx`、`YuantaOrd64.ocx`、`YuantaCAPIDLL*.dll`、
  `YuantaCAPIServiSignAdapterSetup.exe`、`Microsoft.WebView2...cab`、`元大行情API.pdf`、`元大BToCAPI格式.pdf`。
- 維持 gitignored（`PUBLICATION_EXCLUDE_MANIFEST.txt` 已含）。

## 16. Remaining blockers（誠實）
- Legacy Quote OSE symbol：**UNRESOLVED**（EasyWin 對照表不在本機 SDK）。
- EasyWin 商品對照表：**UNRESOLVED**（需 EasyWin 匯出或營業員）。
- SPARK 0112 額外說明：**UNRESOLVED**（需 SPARK 文件）。
- 7xxx 規則：僅歷史 PDF，本機 SDK 無（與現行無關）。

## ACTIONABLE_FINDING（供下一棒，不自動登入）
1. SPARK OSE Micro StkCode **已確定** = `JNU<合約月>`（報價）/ `JNU`（下單），可安全寫入接線。
2. Legacy Quote 期貨 Symbol = **EASYWIN 代碼**（語義確定），取得 EasyWin 對照表即可補齊 legacy symbol。
3. Trading API 需 CA 憑證（`YuantaCAPIServiSignAdapterSetup.exe`）＋ 元大歸戶 ID/密碼；帳號格式 = 分公司(3)+帳號(7)+子帳號(4)。

## Gate
- 只讀鑑識完成；無真實登入 / 下單 / 訂閱 / 帳戶查詢 / SDK 修改 / git push。
- Legacy OSE symbol 誠實標 **UNRESOLVED**（符合 gate 條件）。
- **PHASE2YH_PASS**。

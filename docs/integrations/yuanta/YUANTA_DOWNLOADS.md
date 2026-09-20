# Yuanta Downloads（元件下載）

> 依官方頁面下載；本專案 Windows 11 主要用 **Python x64 SPARK package**。

## SPARK（元大證券）
| 要下載 | 用途 |
|---|---|
| Python Windows **x64** | **本專案主要使用**（證券 Spark，64-bit 主環境） |
| Python Windows x86 | 32-bit 環境用（如需要） |
| C# | C# 開發 |
| COM | COM 整合 |
| 測試軟體 / 測試憑證 | 測試環境 |

下載後解壓，`YuantaSparkAPI.dll`（v2.2026.0918.0）放 `vendor/yuanta_spark/<version>/`（gitignored）。

## Futures Legacy API（元大期貨）
| 項目 | 版本 |
|---|---|
| 交易 API | **1.6.1.3**（官方公開頁） |
| 行情 API | 公開頁 **2.1.2.7** |

⚠️ **本機已觀察到 `YuantaQuote_v2.1.2.9.ocx`**（與公開頁 2.1.2.7 不同）：
- `PUBLIC_PAGE_VERSION != LOCAL_OBSERVED_VERSION`。
- **不要把網頁版本自動當最新版**。
- 以 local package hash + version 作 reproducibility pin。

## 交易 API（1.6.1.3）— FUTURE_RESEARCH_ONLY
- C# sample、Python trading sample。
- 需「API 交易服務風險預告暨申請使用聲明書」+ 申請核准。
- 本棒**不接 runtime、不登入、不測 order**。

## 連線資訊 + 元件註冊（Phase 2Y-H 鑑識 VERIFIED）
| API | Domain | Port | 登入方法 | OCX / ProgID |
|---|---|---|---|---|
| Legacy Quote | `apiquote.yuantafutures.com.tw` | T=80/443, T+1=82/442 | `SetMktLogon(身份證ID, 密碼, ip, port, reqType)` | `YuantaQuote_v2.1.2.9.ocx` / `YUANTAQUOTE.YuantaQuoteCtrl.1` |
| Legacy Trading | `api.yuantafutures.com.tw`（測試 `apitest...`） | 80/443 | `SetFutOrdConnection(歸戶ID, 密碼, ip, port)` | 32-bit `YuantaOrd.ocx`/`Yuanta.YuantaOrdCtrl.1`，64-bit `YuantaOrd64.ocx`/`Yuanta.YuantaOrdCtrl.64` |

- 安裝：`regsvr32 <ocx>`（需系統管理員）；Quote 元件放 `C:\Yuanta\QAPI`，Trading 放 `C:\Yuanta\API`（或 `API_x64`）。
- VC runtime：缺 `vcredist_x86.exe` 時需先裝（安裝失敗解法見官方 `使用說明.txt`）。
- Python 範例環境：**3.9 + wxPython 4.1.1 + comtypes 1.1.11**；bitness 須與 OCX 一致。
- 完整元件盤點見 `YUANTA_LOCAL_SDK_INVENTORY.json`（227 檔案 + SHA256）。

## 憑證
- 元大憑證非 MARKET_AI_HUB 產生；從「元大官方憑證中心」申請/更新/匯出/匯入。
- 見 `docs/YUANTA_CERTIFICATE_WINDOWS11.md`。

## 相關
- `config/yuanta_official_sources.yaml`（官方來源 ground truth）
- `scripts/setup_yuanta_futures_x86.ps1`（x86 sidecar 一鍵重建）
- `scripts/check_yuanta_futures_com.ps1`（COM 診斷）

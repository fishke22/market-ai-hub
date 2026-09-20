# Yuanta Support Evidence Packet（給營業員/客服，無 PII）

## 基本資訊
| 項目 | 值 |
|---|---|
| API family | 多套（SPARK + Legacy Quote COM + Legacy Trading） |
| SPARK component | YuantaSparkAPI.dll v2.2026.0918.0 |
| Legacy Quote component | YuantaQuote_v2.1.2.9.ocx (x86) |
| Trading API | 1.6.1.3（未接線） |
| Environment | PROD（正式環境，runtime enum=2） |
| Masked account | （不在此文件，以 WinCred mask 顯示） |

## 實測結果（sanitized）
| 測試 | 結果 |
|---|---|
| SPARK Securities login | SUCCESS（`MsgCode=0001`） |
| SPARK Futures login | `0112`（無此權限使用功能） |
| Legacy Quote T 盤 | `使用者無登入權`（status=-2） |
| Legacy Quote T+1 盤 | `登入成功`（status=2） |
| Certificate | （見 `scripts/check_yuanta_certificate.ps1` 輸出） |

## 使用者聲明
「元大期貨 API 權限已經全部開通。」

## 請問客服/營業員（照念）
1. 請確認此期貨帳號的 SPARK API Futures 權限是否啟用？（SPARK Login 回 0112）
2. 請確認 T / T+1 Legacy Quote 登入權限。
3. 請確認 OSE / JNU（大阪微日經）行情權限與是否需額外訂閱。
4. Legacy Quote 的「登入ID」是否為身份證字號（而非期貨帳號）？
5. 若需要登入ID，我的登入ID格式為何？（不在此文件記錄）

## 重要
- 本文件**不含** full account / password / 身份證 / certificate info。
- 使用者可自行把 masked account 補上再交給客服。

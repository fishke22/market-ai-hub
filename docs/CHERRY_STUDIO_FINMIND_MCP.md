# CHERRY_STUDIO_FINMIND_MCP — 讓 Cherry Studio 直連 FinMind

## 1. 申請 FinMind token（免費）

1. 到 https://finmindtrade.com
2. 註冊帳號 → 登入 → 個人頁面取得 API token
3. 免費帳號即可使用 Free tier 資料（台灣股價、財報、三大法人等）

## 2. Cherry Studio 設定

| 欄位 | 值 |
|------|-----|
| Name | `finmind` |
| Type / 類型 | `stdio` |
| Command | `uvx` |
| Args | `finmind-mcp` |
| Environment | `FINMIND_TOKEN` = `<你自己申請的 token>` |

**不要把真的 token 寫進任何文件或 commit 到 git。** 只在 Cherry Studio 的設定畫面填入。

## 3. 預期結果

連線成功後，Cherry Studio 會出現 finmind 的工具（查詢 FinMind 各 dataset）。

## 4. 兩者的分工

| MCP | 用途 |
|-----|------|
| `market-ai` | 台股 + 大阪日經 AI 預測中樞（模型 ensemble、backtest、health） |
| `finmind` | FinMind 原始資料查詢（財報、法人買賣、融資券……） |

兩個可以同時啟用，互不衝突。

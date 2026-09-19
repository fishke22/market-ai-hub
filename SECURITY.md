# SECURITY

## 絕對不要提交（commit）的內容

- `.env` 或任何 `*.key` / `*.pem` / `*.pfx` / `*.crt`
- API token（FinMind / FRED / Hugging Face / GitHub / OpenAI 等）
- 券商憑證、帳號密碼、cookie、session
- 個人資訊（email、Windows 使用者名稱、私人絕對路徑）
- 模型 weights / checkpoint（`*.pth` / `*.safetensors` / `*.pt` / `*.onnx`）
- 市場原始資料（`*.parquet` / `*.duckdb` / `*.sqlite`）
- 日誌（`logs/`、`*.log`）

本專案 `.gitignore` 已預設排除上述項目。`.env.example` 只含空 placeholder，可安全提交。

## 本專案如何處理 secrets

- `FINMIND_TOKEN` / `FRED_API_KEY` / `HF_TOKEN` 一律從環境變數或 `.env` 讀取，
  **不寫入程式碼**。
- 程式與文件**不會要求你貼入 token**；需要登入時使用官方 CLI（如 `huggingface-cli login`、
  `gh auth login`）以瀏覽器授權。
- 若你在聊天或文件中看到疑似真實 token，請立即**輪替（rotate）**該 token。

## 提交前自我檢查

```powershell
git status
git diff --cached
```

確認沒有 `.env`、`*.key`、model weights、logs、cache、私人資料被 staged。
若不慎已 commit secret：**不要只刪檔再 commit**（Git history 仍保留）。
請立刻輪替該 secret，並考慮重寫 history（`git filter-repo`）。

## 如何回報安全問題

若發現本專案的安全問題（例如不慎外洩的憑證、依賴漏洞），請**不要**開公開 issue 附上敏感細節；
請透過 GitHub 的私人管道（Security Advisories）或私下聯絡維護者。

## 依賴安全

- 依賴版本鎖定於 `requirements-lock-windows-x64.txt`。
- 更新依賴前請先跑 `pytest` 與 `scripts/verify_install.ps1`。

## 系統邊界（設計上就不存在的能力）

本系統**沒有**：券商登入、下單、資金操作、即時交易執行、憑證存取。
任何聲稱本系統可下單的用法都非本專案設計。

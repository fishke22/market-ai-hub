# 使用方式

1. 將 **00_PROJECT_INSTRUCTIONS.txt** 全文貼到 ChatGPT 專案設定的「指令」。
2. 將 **01_CONTEXT_SNAPSHOT.md、02_ROADMAP.md、03_AUDIT_AND_REPAIRS.md** 上傳同一專案「資料來源」。
3. 在該專案新對話貼 **04_NEW_CHAT_PROMPT.txt**，它接續修補後的下一工作包。
4. 每個工作包發布後更新 CONTEXT，替換過期資料來源；不要期待聊天記憶代替版本化交接。

本包是在實際修補與驗證之後生成。已修、尚未實機套用、未實作與市場證據不足分開列在03。完整規劃與免費第一方來源在02。

你的截圖顯示「僅限專案記憶」及「庫存取權已停用」，不能把後者讀成所有專案記憶停用；不論介面記憶是否可用，都使用檔案交接。參考 [ChatGPT Projects](https://help.openai.com/en/articles/10169521-projects-in-chatgpt)。

此次已能直接在 Codex 施工，因此不另外產生過期的 OpenCode 修補 prompt。04 已規定網頁版 Remote 真正失敗時，依當時實測生成適配 OpenCode / DeepSeek 的自足 prompt；不預先假定模型 ID 或 variant。

只需上傳上述三份 Markdown，不上傳測試暫存、備份、AUDIT_EVIDENCE.json 或真實行情/憑證。ZIP 只含六份交付文件與SHA256 manifest。現有 ChatGPT/Remote/DeepSeek 帳號費與 API 配額不保證免費；本規劃未新增付費服務。
修補 commit：3ea367ab4d5f5cd224857d6a8c8c04dc64f550d2（實作與測試基準）；PR：https://github.com/fishke22/market-ai-hub/pull/55（OPEN，尚未合併 main）；CI：GitHub lightweight CI 發布時執行中；以 PR checks 為準，未宣稱通過；remote：codex/quote-hub-correctness 已推送並核對 SHA；main 基準仍為 eb9202a。

# 第一次使用，從這裡開始

> 這份文件給**完全不懂程式**的人。看完這頁，你就知道 MARKET_AI_HUB 是什麼、能做什麼、不能做什麼。

---

## MARKET_AI_HUB 是什麼？

一個**金融研究工具箱**。它不是：

- ❌ 不是會自動幫你下單的機器人
- ❌ 不是會自己偷偷變聰明的 AI
- ❌ 不是「保證賺錢」的程式
- ✅ 是：讓 AI（例如 Cherry Studio 裡的對話）可以查資料、跑模型、做研究的後端工具。

## 它目前在做什麼？

研究**大阪日經（Nikkei 225 Micro Futures）**這個市場，看模型能不能預測它的走勢。

**目前的誠實結論：模型「有一點統計上的預測能力」，但還「不能拿來交易」。**

## 你需要哪些東西？

| 東西 | 一定要嗎 | 說明 |
|------|---------|------|
| 這台電腦（Windows） | 要 | 程式跑在你電腦上 |
| Cherry Studio | 建議 | 用對話方式使用，不用記指令 |
| Python 3.12 | 要 | 安裝時會用到 |
| Yuanta（元大） | 不用 | 可選，目前沒接交易 |
| TradingView | 不用 | 可選，免費版有延遲 |

## 每天怎樣用？

**最簡單：打開 Cherry Studio，問一句話。**

例如：「幫我分析今天大阪日經。」

AI 會自己去查資料、跑模型、回報結果。你**不需要記任何指令**。

## 先記住三件事

1. **系統不會自己下單。** 完全沒有交易功能。
2. **系統不會自己偷偷訓練。** 目前 AUTO_TRAIN 是關閉的。
3. **模型目前的預測「只是研究參考」，不能當交易建議。**

## 下一步看什麼？

- 想懂系統怎麼運作 → [HOW_MARKET_AI_HUB_WORKS.md](HOW_MARKET_AI_HUB_WORKS.md)
- 想在 Cherry Studio 用 → [CHERRY_STUDIO_BEGINNER_GUIDE.md](CHERRY_STUDIO_BEGINNER_GUIDE.md)
- 想懂每天該做什麼 → [DAILY_WORKFLOW_FOR_BEGINNERS.md](DAILY_WORKFLOW_FOR_BEGINNERS.md)
- 想懂資料要不要手動更新 → [DATA_UPDATE_FOR_BEGINNERS.md](DATA_UPDATE_FOR_BEGINNERS.md)
- 想懂系統何時學習 → [AUTO_LEARNING_FOR_BEGINNERS.md](AUTO_LEARNING_FOR_BEGINNERS.md)
- 想懂離「可交易」還有多遠 → [TRADING_READINESS_FOR_BEGINNERS.md](TRADING_READINESS_FOR_BEGINNERS.md)
- 想懂電腦資源會不會被吃滿 → [SAFE_TRAINING_FOR_BEGINNERS.md](SAFE_TRAINING_FOR_BEGINNERS.md)
- 常見問題 → [FAQ_BEGINNER.md](FAQ_BEGINNER.md)

> **技術使用者**：想讓 AI 遵守嚴謹的金融分析規則，可參考推薦的
> [System Prompt V4（Phase 2 RC1）](prompts/SYSTEM_PROMPT_V4_PHASE2_RC1.md)。
> 一般使用者不需要自己設定，AI Client 會依工具自動運作。

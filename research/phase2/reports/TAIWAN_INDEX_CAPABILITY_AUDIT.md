# Taiwan Index Capability Audit

**Phase 2Q-C §6** — 確認 TAIEX / TX / MTX / TMF 是否真正 first-class，而不只是 prompt 有寫。

## 語義（§2）

| 名稱 | 語義 |
|------|------|
| TAIEX | cash index forecast target / reference（**非可成交**） |
| TX | TAIFEX large index futures（multiplier 200） |
| MTX | mini futures（multiplier 50） |
| TMF | micro futures（multiplier 10） |

Forecast target（TAIEX）與 execution instrument（TX/MTX/TMF）分開。TAIEX 指數點位不可冒充可成交 futures price。

## Capability Matrix

| 能力 | OSAKA_MICRO | TAIWAN_STOCK | TAIWAN_INDEX |
|------|-------------|--------------|--------------|
| data | IMPLEMENTED（JPX settlement + 225LABO LOCAL_ONLY） | PARTIAL（FinMind/TWSE 個股，無 historical adjusted 全量） | MISSING（無 TAIEX/TX/MTX/TMF pipeline） |
| features | IMPLEMENTED | PARTIAL | MISSING |
| models | IMPLEMENTED（VAR + price/direction） | PARTIAL（共用 baseline classifier，無 per-stock historical fit） | MISSING |
| analysis packet | IMPLEMENTED（get_analysis_packet market=osaka） | PARTIAL（market=taiwan 可跑，但無 index 語義） | MISSING（無 market=taiwan_index） |
| historical validation | IMPLEMENTED（Proxy + Direct Micro bar OOS） | MISSING（無 basket historical OOS） | MISSING |
| forward validation | IMPLEMENTED（shadow） | PARTIAL（registry 可註冊，無 per-family 統計） | MISSING |
| strategy research | IMPLEMENTED（NO_ECONOMIC_EDGE） | MISSING | MISSING |

## 結論

- **TAIWAN_INDEX 目前為 MISSING**：不存在真正 TAIEX analysis pipeline，只有 symbol 語義定義。
- 本棒建立語義 + registry + evidence schema，但**不假裝** TAIWAN_INDEX 已 validated。
- 下一棒（Phase 2Q-D+）才做 TAIWAN_INDEX data/model/packet 實際實作；本棒只建立公平框架。

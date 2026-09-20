# Product Spec Audit

**Phase 2Q-C.1 §1** — execution instrument 的 tick / multiplier / exchange / currency authoritative spec audit。
來源用 official exchange documentation，不用 prompt / 舊 report / LLM memory。

verified_at: 2026-09-20

| target | field | current (audit 前) | official value | source | status |
|--------|-------|--------------------|----------------|--------|--------|
| OSE_NIKKEI225_MICRO_FUTURES | multiplier | 100 | **10**（Nikkei 225 × JPY 10） | JPX official: jpx.co.jp/english/derivatives/products/domestic/225micro-futures/01.html | **FIXED** |
| OSE_NIKKEI225_MICRO_FUTURES | tick | 5 | 5（¥50 per tick） | JPX official（同上） | VERIFIED |
| TX (TAIFEX 臺股指數期貨 FITX) | multiplier | 200 | 200（NTD 200 × per point） | TAIFEX official | VERIFIED |
| TX | tick | 1 | 1 point（NTD 200） | TAIFEX official | VERIFIED |
| MTX (小型臺指) | multiplier | 50 | 50 | TAIFEX official | VERIFIED |
| MTX | tick | 1 | 1 point（NTD 50） | TAIFEX official | VERIFIED |
| TMF (微型臺指) | multiplier | 10 | 10（NTD 10 per point） | TAIFEX press release: Micro TAIEX Futures | VERIFIED |
| TMF | tick | 1 | 1 point | TAIFEX press release | VERIFIED |

## Notional sanity（§2）

- OSE Micro @ 65,000 pts：65,000 × **10** = **650,000 JPY**（不得 6,500,000）。
- TX @ 20,000 pts：20,000 × 200 = 4,000,000 NTD。
- MTX @ 20,000 pts：20,000 × 50 = 1,000,000 NTD。
- TMF @ 20,000 pts：20,000 × 10 = 200,000 NTD。

## 唯一錯誤

OSE_NIKKEI225_MICRO_FUTURES multiplier 100 → **10**（已修）。其餘 TX/MTX/TMF 及 tick 全數 authoritative verified。

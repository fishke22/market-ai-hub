"""下載 MARKET_AI_HUB 所需模型（讀 config/model_manifest.yaml）。

用法：
  python scripts/download_models.py --check       # 只檢查是否已存在
  python scripts/download_models.py --download    # 下載缺少的模型（pin revision）

特性：
- 不把任何 token 寫進 source；若 repo 需要授權，使用官方 `huggingface-cli login`。
- 優先 pin manifest 內的 revision（重現 V1 當時版本）。
- 顯示估計磁碟需求。
- weights 只存本地 cache，永不 commit（見 .gitignore）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MANIFEST = ROOT / "config" / "model_manifest.yaml"
MODEL_CACHE_ROOT = ROOT / "models" / "cache"


def _hf_cache_dir() -> Path:
    import os

    return Path(os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME") or (Path.home() / ".cache" / "huggingface"))


def _local_snapshot_dir(logical_name: str, model_id: str) -> Path:
    slug = "models--" + model_id.replace("/", "--")
    return MODEL_CACHE_ROOT / logical_name / slug / "snapshots"


def load_manifest() -> list[dict]:
    import yaml

    with open(MANIFEST, encoding="utf-8") as f:
        return yaml.safe_load(f)["models"]


def check_model(m: dict) -> tuple[bool, str]:
    """檢查模型是否已存在（依 revision）。"""
    model_id = m["model_id"]
    rev = m.get("revision", "")
    if m["logical_name"] == "fincast":
        snap_root = _hf_cache_dir() / "hub" / ("models--" + model_id.replace("/", "--")) / "snapshots"
    else:
        snap_root = _local_snapshot_dir(m["logical_name"], model_id)
    if not snap_root.exists():
        return False, f"not found under {snap_root}"
    if rev and (snap_root / rev).exists():
        return True, f"present (revision {rev[:12]})"
    dirs = [d.name for d in snap_root.iterdir() if d.is_dir()]
    if dirs:
        return True, f"present (revision {dirs[0][:12]}; manifest expects {rev[:12]})"
    return False, "snapshot dir empty"


def download_model(m: dict) -> str:
    from huggingface_hub import hf_hub_download, snapshot_download

    model_id = m["model_id"]
    rev = m.get("revision") or None
    if m["logical_name"] == "fincast":
        path = hf_hub_download(repo_id=model_id, filename="v1.pth", revision=rev)
        return f"downloaded {model_id}/v1.pth -> {path}"
    dest = MODEL_CACHE_ROOT / m["logical_name"]
    dest.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=model_id, revision=rev, cache_dir=str(dest))
    return f"downloaded {model_id} -> {dest}"


def main() -> int:
    ap = argparse.ArgumentParser(description="MARKET_AI_HUB model downloader")
    ap.add_argument("--check", action="store_true", help="只檢查模型是否存在")
    ap.add_argument("--download", action="store_true", help="下載缺少的模型")
    ap.add_argument("--list", action="store_true", help="列出 manifest 所有模型")
    ap.add_argument("--required", action="store_true", help="只處理 required 模型")
    ap.add_argument("--optional", action="store_true", help="只處理 optional 模型")
    args = ap.parse_args()
    if not (args.check or args.download or args.list):
        ap.print_help()
        return 1

    models = load_manifest()
    if args.required:
        models = [m for m in models if m.get("required")]
    elif args.optional:
        models = [m for m in models if not m.get("required")]

    if args.list:
        for m in models:
            print(f"{m['logical_name']:<14} {'REQUIRED' if m.get('required') else 'OPTIONAL':<9} "
                  f"~{m.get('estimated_size_mb','?')}MB  {m['model_id']}")
        return 0

    print("=" * 70)
    print("MARKET_AI_HUB model manifest")
    print("=" * 70)
    total_mb = 0
    missing = []
    for m in models:
        ok, detail = check_model(m)
        req = "REQUIRED" if m.get("required") else "OPTIONAL"
        size = m.get("estimated_size_mb", "?")
        total_mb += int(size) if str(size).isdigit() else 0
        print(f"[{'OK ' if ok else 'MISS'}] {m['logical_name']:<14} {req:<9} ~{size}MB  {detail}")
        if not ok:
            missing.append(m)

    print("-" * 70)
    print(f"estimated disk for all models: ~{total_mb} MB")
    print("授權注意：TimesFM-3.0 與 FinCast weights 不可重新散布（見 THIRD_PARTY_NOTICES.md）")

    if args.check:
        return 0 if not missing else 2

    if args.download:
        if not missing:
            print("all models present; nothing to download")
            return 0
        print(f"\n下載 {len(missing)} 個缺少模型（pin revision）...")
        print("若出現 401/403 或 gated repo：請先執行 `huggingface-cli login`（瀏覽器登入），")
        print("不要在本程式或任何檔案中貼入 token。")
        for m in missing:
            try:
                print(" -", download_model(m))
            except Exception as e:
                print(f"   FAILED {m['logical_name']}: {e}")
        # 重新檢查
        still = [m["logical_name"] for m in models if not check_model(m)[0]]
        if still:
            print("STILL MISSING:", still)
            return 2
        print("all models downloaded")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

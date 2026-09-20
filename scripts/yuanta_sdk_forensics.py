"""Phase 2Y-H — Yuanta local SDK forensics (READ-ONLY inventory).

Recursively inventories the user's official Yuanta SDK directories, computes SHA256,
and writes YUANTA_LOCAL_SDK_INVENTORY.json. Never modifies / registers / executes anything.

禁止：刪除/改名/註冊/執行交易 sample/覆寫/搬移/登入/下單。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

ROOTS = [
    r"C:\Users\fishk\Documents\元大期貨API",
    r"C:\Users\fishk\Downloads\元大期貨元件",
    r"C:\Users\fishk\Downloads\元大證券元件",
]

INTERESTING = {".dll", ".ocx", ".tlb", ".exe", ".py", ".cs", ".cpp", ".h", ".pdf",
               ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".ini", ".cfg",
               ".xml", ".json", ".reg", ".bat", ".ps1", ".zip", ".cab"}


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory() -> list[dict]:
    out = []
    for root in ROOTS:
        for dp, dn, fn in os.walk(root):
            for name in fn:
                full = os.path.join(dp, name)
                try:
                    st = os.stat(full)
                    rel = os.path.relpath(full, root)
                    out.append({
                        "root": os.path.basename(root),
                        "relative_path": rel.replace("\\", "/"),
                        "filename": name,
                        "size": st.st_size,
                        "modified_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                        "extension": os.path.splitext(name)[1].lower(),
                        "sha256": sha256_of(full),
                    })
                except Exception as e:
                    out.append({"root": os.path.basename(root), "relative_path": rel, "error": str(e)})
    return out


def main():
    recs = inventory()
    recs.sort(key=lambda r: (r["root"], r["relative_path"]))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "roots": ROOTS,
        "total_files": len(recs),
        "files": recs,
        "interesting_count": sum(1 for r in recs if r.get("extension") in INTERESTING),
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "YUANTA_LOCAL_SDK_INVENTORY.json")
    out = os.path.normpath(out)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {out} ({len(recs)} files)")


if __name__ == "__main__":
    main()

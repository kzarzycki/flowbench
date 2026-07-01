import json
import sys
from pathlib import Path

STORE = Path("tasks.json")


def _load():
    if STORE.exists():
        return json.loads(STORE.read_text())
    return {"next_id": 1, "tasks": []}


def _save(db):
    STORE.write_text(json.dumps(db))


def main(argv):
    db = _load()
    if not argv:
        print("usage: todo {add|list|done|rm}", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "add":
        db["tasks"].append(
            {"id": db["next_id"], "text": rest[0], "status": "open", "priority": "med"}
        )
        db["next_id"] += 1
        _save(db)
    elif cmd == "list":
        for t in db["tasks"]:
            mark = "✓" if t["status"] == "done" else " "
            print(f"[{mark}] {t['id']} ({t['priority']}) {t['text']}")
    elif cmd == "done":
        tid = int(rest[0])
        for t in db["tasks"]:
            if t["id"] == tid:
                t["status"] = "done"
        _save(db)
    elif cmd == "rm":
        tid = int(rest[0])
        db["tasks"] = [t for t in db["tasks"] if t["id"] != tid]
        _save(db)
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

import sys

TASKS = []  # in-memory only: lost when the process exits


def main(argv):
    if not argv:
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "add":
        TASKS.append({"id": len(TASKS) + 1, "text": rest[0], "status": "open"})
    elif cmd == "list":
        for t in TASKS:
            print(f"{t['id']} {t['text']}")
    elif cmd in ("done", "rm"):
        pass
    else:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

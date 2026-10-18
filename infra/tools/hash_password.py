#!/usr/bin/env python3
"""Create one demo-users JSON value without keeping the plaintext anywhere."""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rag-api"))

from app.auth import hash_password


def main() -> int:
    if len(sys.argv) != 1:
        print("usage: tools/hash_password.py", file=sys.stderr)
        return 2
    password, repeat = getpass.getpass("Password: "), getpass.getpass("Confirm password: ")
    if password != repeat:
        print("passwords do not match", file=sys.stderr)
        return 1
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

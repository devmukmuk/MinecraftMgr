#!/usr/bin/env python3
"""Extract Minecraft user login (and optionally unauthorized-attempt) timestamps from server logs.

Imported from oscar on 2026-08-18. This file was byte-identical across
/opt/mc/{arbor_1_21_10,gravestone_26_1_2,river_1_21_1}/extract-user-data.py
(md5 8dd66a5efe7e34b6d910d8b3c9158ace) -- consolidated to this one tracked
copy. See tools/scripts/README.md.
"""
import argparse
import os
import re
import gzip
from datetime import datetime
from collections import defaultdict

# Regex patterns
FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

# Successful login example:
# [12:34:56] [Server thread/INFO]: PlayerName joined the game
LOGIN_RE = re.compile(r"\[(\d{2}:\d{2}:\d{2})\].*?: (\w+) joined the game")

# Unauthorized attempts examples:
# [WARN]: User 'Bob' tried to join but is not authorized
# [WARN]: Couldn't verify username 'Bob'
UNAUTH_RE = re.compile(
    r"\[(\d{2}:\d{2}:\d{2})\].*?(?:User|username|player)[ '\"]+(\w+)[ '\"]+.*?(?:not authorized|Couldn't verify)",
    re.IGNORECASE
)

def get_date_from_filename(filename):
    """Return the YYYY-MM-DD date prefix from a rotated log filename, or None."""
    match = FILENAME_DATE_RE.match(filename)
    if match:
        return match.group(1)
    return None

def open_log_file(path):
    """Open a log file for reading text, transparently handling .gz rotation."""
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="ignore")
    return open(path, "r", encoding="utf-8", errors="ignore")

def process_logs(log_dir, include_unauthorized):
    """Scan every .log/.gz file in log_dir, returning {user: [timestamps]} for
    successful joins and, if requested, unauthorized join attempts."""
    user_logins = defaultdict(list)
    unauthorized_logins = defaultdict(list)

    for filename in sorted(os.listdir(log_dir)):
        full_path = os.path.join(log_dir, filename)

        if not os.path.isfile(full_path):
            continue

        if not (filename.endswith(".log") or filename.endswith(".gz")):
            continue

        file_date = get_date_from_filename(filename)

        with open_log_file(full_path) as f:
            for line in f:

                # Successful login
                m = LOGIN_RE.search(line)
                if m:
                    time_str, user = m.group(1), m.group(2)
                    if file_date:
                        dt = datetime.strptime(f"{file_date} {time_str}", "%Y-%m-%d %H:%M:%S")
                        user_logins[user].append(dt)
                    continue

                # Unauthorized attempt
                if include_unauthorized:
                    u = UNAUTH_RE.search(line)
                    if u:
                        time_str, user = u.group(1), u.group(2)
                        if file_date:
                            dt = datetime.strptime(f"{file_date} {time_str}", "%Y-%m-%d %H:%M:%S")
                            unauthorized_logins[user].append(dt)
                        continue

    return user_logins, unauthorized_logins


def main():
    """Parse CLI args, run the log scan, and print results grouped by user."""
    parser = argparse.ArgumentParser(description="Extract Minecraft user logins from logs.")
    parser.add_argument(
        "--log-dir",
        default=".",
        help="Directory containing Minecraft logs (default: current directory)"
    )
    parser.add_argument(
        "--unauthorized",
        action="store_true",
        help="Include unauthorized login attempts"
    )

    args = parser.parse_args()

    user_logins, unauthorized_logins = process_logs(args.log_dir, args.unauthorized)

    # Successful logins
    for user in sorted(user_logins):
        print(f"\n=== {user} (authorized) ===")
        for dt in sorted(user_logins[user]):
            print(dt.isoformat(" "))

    # Unauthorized logins (only if requested)
    if args.unauthorized:
        for user in sorted(unauthorized_logins):
            print(f"\n=== {user} (UNAUTHORIZED) ===")
            for dt in sorted(unauthorized_logins[user]):
                print(dt.isoformat(" "))


if __name__ == "__main__":
    main()

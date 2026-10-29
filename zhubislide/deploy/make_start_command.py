"""Print the Railway start command that runs a given commit of this repo (see HANDOFF.md, "Ship an update").

    python deploy/make_start_command.py $(git rev-parse HEAD)
"""
import base64
import re
import sys
from pathlib import Path

if len(sys.argv) != 2 or not re.fullmatch(r"[0-9a-f]{40}", sys.argv[1]):
    sys.exit("usage: python deploy/make_start_command.py <full 40-character commit SHA>")
boot = Path(__file__).with_name("railway_boot.py").read_text()
boot = re.sub(r"tar\.gz/[0-9a-f]{40}", f"tar.gz/{sys.argv[1]}", boot)
print(f"python -c \"exec(__import__('base64').b64decode('{base64.b64encode(boot.encode()).decode()}'))\"")

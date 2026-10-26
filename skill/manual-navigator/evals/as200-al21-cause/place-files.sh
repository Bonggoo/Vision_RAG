#!/usr/bin/env bash
# Builds the fictional manual library into ./manuals (no ground truth is written here).
set -eu
python3 "$(dirname "$0")/../make_samples.py" manuals > /dev/null

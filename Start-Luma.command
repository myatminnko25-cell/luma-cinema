#!/bin/zsh
cd "$(dirname "$0")"
export LUMA_HOST=0.0.0.0
python3 server.py

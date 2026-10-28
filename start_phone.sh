#!/bin/bash
# FeTAp 791 Startup Wrapper
cd /home/paimon/fetap791_ai || exit 1
source venv/bin/activate
exec python3 pi_fetap_live.py

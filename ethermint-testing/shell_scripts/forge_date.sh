#!/usr/bin/env bash
set -euo xtrace

echo "date before forging:"
date

sudo date -u -s $1

echo "after date forged:"
date

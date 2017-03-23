#!/usr/bin/env bash

echo "date before forging:"
date

sudo date -u -s $1

echo "after date forged:"
date

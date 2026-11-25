"""
File: stage2_no_edge_stop.py
Description: Broken Pong stage 2 program: q wraps the left paddle from the
    top to the bottom instead of stopping.
Author(s): Richard Hall
"""

import sys

PADDLE = 3
left = 8
right = 8
for line in sys.stdin:
    keys = line.strip()
    if "q" in keys:
        left = (left - 1) % (21 - PADDLE)
    if "a" in keys:
        left = min(20 - PADDLE, left + 1)
    if "p" in keys:
        right = max(0, right - 1)
    if "l" in keys:
        right = min(20 - PADDLE, right + 1)
    for row in range(20):
        cells = ["."] * 20
        if left <= row < left + PADDLE:
            cells[0] = "|"
        if right <= row < right + PADDLE:
            cells[19] = "|"
        if row == 9:
            cells[9] = "O"
        print("".join(cells))
    print("---")

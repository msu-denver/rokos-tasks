"""
File: stage2_wrong_paddle.py
Description: Broken Pong stage 2 program: q moves the right paddle.
Author(s): Richard Hall
"""

import sys

PADDLE = 3
left = 8
right = 8
for line in sys.stdin:
    keys = line.strip()
    if "q" in keys:
        right = max(0, right - 1)
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

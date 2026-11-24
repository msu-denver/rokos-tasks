"""
File: stage3_score_wrong_side.py
Description: Broken Pong stage 3 program: the side that misses gets the
    point.
Author(s): Richard Hall
"""

import sys

PADDLE = 3
left = 8
right = 8
ball_row = 9
ball_col = 9
step_row = 1
step_col = 1
scores = [0, 0]

for line in sys.stdin:
    keys = line.strip()
    if "q" in keys:
        left = max(0, left - 1)
    if "a" in keys:
        left = min(20 - PADDLE, left + 1)
    if "p" in keys:
        right = max(0, right - 1)
    if "l" in keys:
        right = min(20 - PADDLE, right + 1)

    if not 0 <= ball_row + step_row <= 19:
        step_row = -step_row
    ball_row += step_row
    next_col = ball_col + step_col
    if next_col <= 0 or next_col >= 19:
        paddle = left if next_col <= 0 else right
        if paddle <= ball_row < paddle + PADDLE:
            step_col = -step_col
            next_col = ball_col + step_col
        else:
            scores[0 if next_col <= 0 else 1] += 1
            ball_row, next_col = 9, 9
            step_col = -step_col
    ball_col = next_col

    for row in range(20):
        cells = ["."] * 20
        if left <= row < left + PADDLE:
            cells[0] = "|"
        if right <= row < right + PADDLE:
            cells[19] = "|"
        if row == ball_row:
            cells[ball_col] = "O"
        print("".join(cells))
    print(scores[0], scores[1])
    print("---")

"""
File: stage3_random_serve.py
Description: Correct Pong stage 3 program (US6 AC3): 2 columns per tick, a
    random start, and a random serve after every point.
Author(s): Richard Hall
"""

import random
import sys

PADDLE = 3
left = random.randint(0, 20 - PADDLE)
right = random.randint(0, 20 - PADDLE)
row = random.randint(0, 19)
column = random.randint(5, 14)
row_step = random.choice([-1, 1])
column_step = random.choice([-2, 2])
score_left = 0
score_right = 0

for line in sys.stdin:
    if "q" in line:
        left = max(0, left - 1)
    if "a" in line:
        left = min(20 - PADDLE, left + 1)
    if "p" in line:
        right = max(0, right - 1)
    if "l" in line:
        right = min(20 - PADDLE, right + 1)
    if not 0 <= row + row_step <= 19:
        row_step = -row_step
    row += row_step
    target = column + column_step
    if target <= 0 or target >= 19:
        top = left if target <= 0 else right
        if top <= row < top + PADDLE:
            column_step = -column_step
            target = column + column_step
        else:
            if target <= 0:
                score_right += 1
            else:
                score_left += 1
            row = random.randint(0, 19)
            target = random.randint(5, 14)
            row_step = random.choice([-1, 1])
            column_step = random.choice([-2, 2])
    column = target
    for board_row in range(20):
        cells = ["."] * 20
        if left <= board_row < left + PADDLE:
            cells[0] = "|"
        if right <= board_row < right + PADDLE:
            cells[19] = "|"
        if board_row == row:
            cells[column] = "O"
        print("".join(cells))
    print(score_left, score_right)
    print("---")

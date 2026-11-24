"""
File: stage1_two_balls.py
Description: Broken Pong stage 1 program: draws two balls.
Author(s): Richard Hall
"""

import sys

for _line in sys.stdin:
    for row in range(20):
        if row == 9:
            print("." * 9 + "OO" + "." * 9)
        else:
            print("." * 20)
    print("---")

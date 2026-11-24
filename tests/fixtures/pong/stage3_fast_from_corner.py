"""
File: stage3_fast_from_corner.py
Description: Correct Pong stage 3 program (US6 AC3): 3 columns per tick,
    starts near a corner, paddles start at the edges, and it is built around
    a class.
Author(s): Richard Hall
"""

import sys

HEIGHT = 20
WIDTH = 20
PADDLE = 3


class Pong:
    """The whole game state, advanced one tick at a time."""

    def __init__(self) -> None:
        """Start near the top-left corner, moving up and to the right."""
        self.paddles = {"left": 0, "right": HEIGHT - PADDLE}
        self.ball = [1, 2]
        self.velocity = [-1, 3]
        self.score = {"left": 0, "right": 0}

    def press(self, keys: str) -> None:
        """Move the paddles for the keys pressed this tick."""
        moves = {"q": ("left", -1), "a": ("left", 1)}
        moves.update({"p": ("right", -1), "l": ("right", 1)})
        for key, (side, step) in moves.items():
            if key in keys:
                top = self.paddles[side] + step
                self.paddles[side] = min(HEIGHT - PADDLE, max(0, top))

    def advance(self) -> None:
        """Move the ball one tick, bouncing or scoring as needed."""
        row, column = self.ball
        if not 0 <= row + self.velocity[0] < HEIGHT:
            self.velocity[0] *= -1
        row += self.velocity[0]
        target = column + self.velocity[1]
        if 0 < target < WIDTH - 1:
            self.ball = [row, target]
            return
        side = "left" if target <= 0 else "right"
        top = self.paddles[side]
        if top <= row < top + PADDLE:
            self.velocity[1] *= -1
            self.ball = [row, column + self.velocity[1]]
            return
        self.score["right" if side == "left" else "left"] += 1
        self.ball = [15, 12]
        self.velocity = [-1, -3]

    def frame(self) -> str:
        """Return the board, the score line, and the frame end."""
        lines = []
        for row in range(HEIGHT):
            cells = ["."] * WIDTH
            for side, column in (("left", 0), ("right", WIDTH - 1)):
                top = self.paddles[side]
                if top <= row < top + PADDLE:
                    cells[column] = "|"
            if row == self.ball[0]:
                cells[self.ball[1]] = "O"
            lines.append("".join(cells))
        lines.append(f"{self.score['left']} {self.score['right']}")
        lines.append("---")
        return "\n".join(lines)


game = Pong()
for line in sys.stdin:
    game.press(line)
    game.advance()
    print(game.frame())

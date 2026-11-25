/*
File: game.js
Description: Initializes the play page from the server-rendered stage
    and connects browser-based Python execution to the game interface.
Author(s): Tyler Black, Richard Hall, Steph Rivera
*/

import {init_editor} from "./editor.js";
import {init_feed} from "./feed.js";
import {init_submit} from "./submit.js";
import {create_player} from "./play.js";

init_feed(document.querySelector(".game-feed"));

const get_code = init_editor(document.querySelector(".game-editor"));

init_submit(
  document.querySelector('[data-testid="game-submit"]'),
  document.querySelector('[data-testid="game-verdict"]'),
  get_code,
);

const run_button = document.querySelector(
  '[data-testid="game-run"]',
);

const stop_button = document.querySelector(
  '[data-testid="game-stop"]',
);

const game_screen = document.querySelector(
  '[data-testid="game-screen"]',
);

const game_error = document.querySelector(
  '[data-testid="game-error"]',
);

const game_timeout = document.querySelector(
  '[data-testid="game-run-timeout"]',
);

const live_panel = document.querySelector(".game-live-panel");


function clear_output() {
  game_screen.textContent = "";
  game_error.textContent = "";
  game_timeout.textContent = "";

  game_error.hidden = true;
  game_timeout.hidden = true;
}

function show_error(error) {
  live_panel.hidden = false;

  if (game_screen.textContent === "Waiting for frame…") {
    game_screen.textContent = "Program stopped.";
  }

  game_error.textContent = error;
  game_error.hidden = false;
  game_error.scrollIntoView({block: "nearest"});
}

const player = create_player({
  on_state(state) {
    run_button.disabled = state !== "ready";
    stop_button.disabled = state !== "running";

    const labels = {
      loading: "Loading Python…",
      ready: "Run",
      running: "Running…",
      restarting: "Restarting Python…",
      unavailable: "Python unavailable",
    };

    run_button.textContent = labels[state] ?? "Run";
  },

  on_frame(frame) {
    game_screen.textContent = frame;
  },

  on_error(error) {
    show_error(error);
  },

  on_timeout(message) {
    live_panel.hidden = false;
    game_timeout.textContent = message;
    game_timeout.hidden = false;
  },

  on_finish(stderr) {
    if (stderr) {
      show_error(stderr);
    }
  },
});


run_button.addEventListener("click", () => {
  clear_output();

  live_panel.hidden = false;
  game_screen.textContent = "Waiting for frame…";

  if (player.run(get_code())) {
    game_screen.focus();
  }
});


stop_button.addEventListener("click", () => {
  player.stop();
});


game_screen.addEventListener("keydown", (event) => {
  if (
    event.ctrlKey ||
    event.metaKey ||
    event.altKey ||
    event.isComposing
  ) {
    return;
  }

  const key = event.key;

  if (key === " " || /^[^\p{C}\p{Z}]$/u.test(key)) {
    event.preventDefault();
    player.queue_key(key);
  }
});


player.init();

/*
File: run_ui.js
Description: Connects local Python execution to the shared game console,
    Run and Stop controls, and interactive player input.
Author(s): Steph Rivera
*/

import {create_player} from "./play.js";

const MAX_INPUT_LENGTH = 64;

function get_parts(root) {
  const part = (id) => root.querySelector(`[data-testid="${id}"]`);

  return {
    run: part("game-run"),
    stop: part("game-stop"),
    submit: part("game-submit"),
    verdict: part("game-verdict"),
    output: part("game-run-output"),
    status: part("game-run-status"),
    screen: part("game-run-screen"),
    error: part("game-error"),
    timeout: part("game-run-timeout"),
    console_body: part("game-console-body"),
    load_error: part("game-run-load-error"),
    hint: part("game-run-hint"),
    form: part("game-run-input-form"),
    input: part("game-run-input"),
    send: part("game-run-send"),
  };
}

function enable_input(parts, enabled) {
  parts.input.disabled = !enabled;
  parts.send.disabled = !enabled;
}

function show_message(element, message) {
  element.textContent = message ?? "";
  element.hidden = !message;
}

function limit_line(input) {
  const characters = Array.from(input.value);

  if (characters.length > MAX_INPUT_LENGTH) {
    input.value = characters.slice(0, MAX_INPUT_LENGTH).join("");
  }
}

function show_load_error(parts, error) {
  parts.load_error.textContent =
    "Python could not load. You can still Submit your code." +
    (error ? ` ${error}` : "");
  parts.load_error.hidden = false;
}

function reset_output(parts, input_style) {
  parts.verdict.hidden = true;
  parts.output.hidden = false;
  parts.status.textContent = "Program running…";
  parts.screen.textContent = "";
  parts.input.value = "";

  show_message(parts.error, "");
  show_message(parts.timeout, "");

  parts.form.hidden = input_style !== "lines";
  parts.hint.hidden = input_style !== "keys";
  enable_input(parts, false);
}

function finish_output(parts, message, error, timeout) {
  parts.status.textContent = message;
  parts.form.hidden = true;
  parts.hint.hidden = true;
  enable_input(parts, false);
  show_message(parts.error, error);
  show_message(parts.timeout, timeout);
}

export function init_run(root, get_code, show_console, input_style) {
  const parts = get_parts(root);
  let state = "idle";
  let submitting = false;

  function update_controls() {
    parts.run.disabled = state !== "ready" || submitting;
    parts.stop.disabled = state !== "running";
    parts.submit.disabled = state === "running" || submitting;

    if (["idle", "loading", "restarting"].includes(state)) {
      parts.run.textContent = "Loading Python…";
    } else if (state === "unavailable") {
      parts.run.textContent = "Python unavailable";
    } else {
      parts.run.textContent = "Run";
    }

    if (state !== "running") {
      enable_input(parts, false);
    }
  }

  function finish(message, error = "", timeout = "") {
    finish_output(parts, message, error, timeout);
    show_console(message);
  }

  const player = create_player({
    on_state(value) {
      state = value;
      update_controls();

      if (state === "ready") {
        parts.load_error.textContent = "";
        parts.load_error.hidden = true;
      }
    },

    on_frame(screen) {
      parts.screen.textContent = screen;
    },

    on_input() {
      parts.status.textContent = "Waiting for input…";
      enable_input(parts, true);
      show_console("Waiting for input.");
      parts.input.focus();
    },

    on_error(error) {
      if (state === "unavailable") {
        show_load_error(parts, error);
        return;
      }

      finish("Program stopped with an error.", error);
    },

    on_timeout(message) {
      finish("Execution timed out.", "", message);
    },

    on_finish(stderr) {
      finish("Program finished.", stderr);
    },
  });

  parts.run.addEventListener("click", () => {
    if (state !== "ready" || submitting) return;
    if (!player.run(get_code(), input_style)) return;

    reset_output(parts, input_style);
    show_console("Program running.");

    if (input_style === "keys") {
      parts.screen.focus();
    }
  });

  parts.stop.addEventListener("click", () => {
    if (state !== "running") return;

    player.stop();
    finish("Program stopped.");
  });

  parts.input.addEventListener("input", (event) => {
    if (!event.isComposing) {
      limit_line(parts.input);
    }
  });

  parts.input.addEventListener("compositionend", () => {
    limit_line(parts.input);
  });

  parts.form.addEventListener("submit", (event) => {
    event.preventDefault();
    limit_line(parts.input);

    if (!player.submit_line(parts.input.value)) return;

    parts.input.value = "";
    parts.status.textContent = "Program running…";
    enable_input(parts, false);
  });

  parts.console_body.addEventListener("keydown", (event) => {
    if (
      state !== "running" ||
      input_style !== "keys" ||
      event.ctrlKey ||
      event.metaKey ||
      event.altKey ||
      event.isComposing
    ) return;

    if (
      event.key !== " " &&
      !/^[^\p{C}\p{Z}]$/u.test(event.key)
    ) return;

    event.preventDefault();
    player.queue_key(event.key);
  });

  function set_submitting(value) {
    submitting = value;

    if (submitting) {
      parts.output.hidden = true;
    }

    update_controls();
  }

  player.init();

  return set_submitting;
}

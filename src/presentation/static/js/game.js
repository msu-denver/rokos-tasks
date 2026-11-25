/*
File: game.js
Description: Initializes the play page from the server-rendered stage.
Author(s): Tyler Black, Steph Rivera, Richard Hall
*/

import {init_editor} from "./editor.js";
import {init_feed} from "./feed.js";
import {init_submit} from "./submit.js";
import {render_results} from "./console.js";

init_feed(document.querySelector(".game-feed"));
const get_code = init_editor(document.querySelector(".game-editor"));

init_submit(
  document.querySelector('[data-testid="game-submit"]'),
  document.querySelector('[data-testid="game-verdict"]'),
  get_code,
);

const run_sample_button = document.querySelector(
  '[data-testid="game-run-sample"]',
);

const sample_console = document.querySelector(
  '[data-testid="game-console"]',
);


const RUN_TIMEOUT_MS = 5000;

const {samples} = JSON.parse(
  document.getElementById("stage-data").textContent,
);


let timeout_id = null;
let worker_url = null;
let workers = [];
let ready_count = 0;
let current_sample = 0;
let results = [];
let player_code = "";


function clear_run_timeout() {
  clearTimeout(timeout_id);
  timeout_id = null;
}

function terminate_workers() {
  workers.forEach((worker) => {
    worker?.terminate();
  });

  workers = [];
  ready_count = 0;
}

function handle_timeout() {
  terminate_workers();
  timeout_id = null;

  run_sample_button.disabled = true;
  run_sample_button.textContent = "Restarting Python…";

  const summary = sample_console.querySelector(
    '[data-testid="game-sample-summary"]',
  );
  const sample_results = sample_console.querySelector(
    ".game-sample-results",
  );

  summary.textContent = "";
  sample_results.replaceChildren();

  const message = document.createElement("p");
  message.dataset.testid = "game-run-timeout";
  message.textContent =
    "Your code ran for more than 5 seconds and was stopped. " +
    "Check for an infinite loop.";

  sample_results.append(message);
  sample_console.hidden = false;

  start_workers();
}

function handle_worker_error(error) {
  const was_running = timeout_id !== null;

  clear_run_timeout();
  terminate_workers();

  const summary = sample_console.querySelector(
    '[data-testid="game-sample-summary"]',
  );
  const sample_results = sample_console.querySelector(
    ".game-sample-results",
  );

  sample_results.replaceChildren();
  summary.textContent = "Python encountered an unexpected error.";
  sample_console.hidden = false;
  sample_console.scrollTop = 0;

  console.error("Python worker failed:", error);

  run_sample_button.disabled = true;

  if (was_running) {
    run_sample_button.textContent = "Restarting Python…";
    start_workers();
  } else {
    run_sample_button.textContent = "Python unavailable";
  }
}

function handle_sample_result(result) {
  results.push(result);
  workers[current_sample].terminate();
  workers[current_sample] = null;

  current_sample++;

  if (current_sample < samples.length) {
    workers[current_sample].postMessage({
      type: "run",
      code: player_code,
      sample: samples[current_sample],
    });
  } else {
    clear_run_timeout();
    render_results(sample_console, results);
    terminate_workers();

    run_sample_button.disabled = true;
    run_sample_button.textContent = "Restarting Python…";

    start_workers();
  }
}

function start_workers() {
  ready_count = 0;
  run_sample_button.disabled = true;

  samples.forEach((sample, index) => {
        const worker = new Worker(
        worker_url,
      {type: "module"},
    );

    workers.push(worker);

    worker.addEventListener("message", (event) => {
      if (workers[index] !== worker) return;

      const {type, error} = event.data;

      if (type === "ready") {
        ready_count++;

        if (ready_count === samples.length) {
          run_sample_button.disabled = false;
          run_sample_button.textContent = "Run Sample";
        }
      } else if (type === "result") {
        handle_sample_result(event.data.result);
      } else if (type === "run_error" || type === "load_error") {
        handle_worker_error(error);
      }
    });

    worker.addEventListener("error", (event) => {
      if (workers[index] !== worker) return;

      handle_worker_error(event.message);
    });
  });
}


async function init_workers() {
  try {
    const response = await fetch(
      new URL("./pyodide_worker.js", import.meta.url),
    );

    if (!response.ok) {
      throw new Error("Unable to load Python worker.");
    }

    const source = await response.text();
    const blob = new Blob([source], {type: "text/javascript"});
    worker_url = URL.createObjectURL(blob);

    start_workers();
  } catch (error) {
    handle_worker_error(error.message);
  }
}

init_workers();


run_sample_button.addEventListener("click", () => {
  player_code = get_code();
  current_sample = 0;
  results = [];

  run_sample_button.disabled = true;
  run_sample_button.textContent = "Running…";

  timeout_id = setTimeout(handle_timeout, RUN_TIMEOUT_MS);

  workers[current_sample].postMessage({
    type: "run",
    code: player_code,
    sample: samples[current_sample],
  });
});


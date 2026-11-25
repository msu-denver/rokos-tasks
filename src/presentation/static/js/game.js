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
let timeout_id = null;

let worker = null;

function start_worker() {
  worker = new Worker(
    new URL("./pyodide_worker.js", import.meta.url),
    {type: "module"},
  );


worker.addEventListener("message", (event) => {
  const {type, error} = event.data;

  if (type === "ready") {
    run_sample_button.disabled = false;
    run_sample_button.textContent = "Run Sample";
    console.log("Python is ready.");
  } else if (type === "results") {
    run_sample_button.disabled = false;
    run_sample_button.textContent = "Run Sample";
    render_results(sample_console, event.data.results);  
  } else if (type === "run_error") {
    run_sample_button.disabled = false;
    run_sample_button.textContent = "Run Sample";
    console.error("Sample execution failed:", error); 
  } else if (type === "load_error") {
    run_sample_button.disabled = true;
    run_sample_button.textContent = "Python unavailable";
    console.error("Failed to load Python:", error);
  }
});


worker.addEventListener("error", (event) => {
  run_sample_button.disabled = true;
  run_sample_button.textContent = "Python unavailable";
  console.error("Python worker failed:", event.message);
});

run_sample_button.addEventListener("click", () => {
  const code = get_code();

  const {samples} = JSON.parse(
    document.getElementById("stage-data").textContent,
  );

  run_sample_button.disabled = true;
  run_sample_button.textContent = "Running…";

  worker.postMessage({
    type: "run",
    code,
    samples,
  });
});


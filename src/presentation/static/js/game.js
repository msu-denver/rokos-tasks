/*
File: game.js
Description: Initializes the play page from the server-rendered stage.
Author(s): Tyler Black, Steph Rivera, Richard Hall
*/

import {init_editor} from "./editor.js";
import {init_feed} from "./feed.js";
import {init_submit} from "./submit.js";

init_feed(document.querySelector(".game-feed"));
const get_code = init_editor(document.querySelector(".game-editor"));

init_submit(
  document.querySelector('[data-testid="game-submit"]'),
  document.querySelector('[data-testid="game-verdict"]'),
  get_code,
);

const worker = new Worker(
  new URL("./pyodide_worker.js", import.meta.url),
  {type: "module"},
);

worker.addEventListener("message", (event) => {
  const {type, error} = event.data;

  if (type === "ready") {
    console.log("Python is ready.");
  } else if (type === "load_error") {
    console.error("Failed to load Python:", error);
  }
});

worker.addEventListener("error", (event) => {
  console.error("Python worker failed:", event.message);
});

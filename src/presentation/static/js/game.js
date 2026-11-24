/*
File: game.js
Description: Initializes the play page from the server-rendered stage.
Author(s): Tyler Black
*/

import {init_editor} from "./editor.js";
import {init_feed} from "./feed.js";

init_feed(document.querySelector(".game-feed"));
init_editor(document.querySelector(".game-editor"));


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

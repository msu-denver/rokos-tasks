/*
File: game.js
Description: Initializes the play page from the server-rendered stage.
Author(s): Tyler Black, Richard Hall, Steph Rivera
*/

import {init_console} from "./console.js";
import {init_editor} from "./editor.js";
import {init_feed} from "./feed.js";
import {init_run} from "./run_ui.js";
import {init_submit} from "./submit.js";

init_feed(document.querySelector(".game-feed"));

const editor = document.querySelector(".game-editor");
const get_code = init_editor(editor);

const show_console = init_console(
  document.querySelector('[data-testid="game-console"]'),
  editor,
);

const stage_data = JSON.parse(
  document.getElementById("stage-data").textContent,
);

const set_submitting = init_run(
  document.querySelector(".game-editor-panel"),
  get_code,
  show_console,
  stage_data.input_style,
);

init_submit(
  document.querySelector('[data-testid="game-submit"]'),
  document.querySelector('[data-testid="game-verdict"]'),
  get_code,
  show_console,
  set_submitting,
);

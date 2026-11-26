/*
File: game.js
Description: Initializes the play page from the server-rendered stage and
    applies each graded Submit to it: the next stage after a pass, the
    reset after a fail, and the result screen when the run ends (US7).
Author(s): Tyler Black, Richard Hall
*/

import {read_stage_data} from "./api.js";
import {init_console} from "./console.js";
import {init_editor} from "./editor.js";
import {init_feed, show_prompt} from "./feed.js";
import {show_lives, show_stage} from "./hud.js";
import {init_submit} from "./submit.js";

const by_test_id = (test_id) =>
  document.querySelector(`[data-testid="${test_id}"]`);

const feed = document.querySelector(".game-feed");
init_feed(feed);
const editor_element = document.querySelector(".game-editor");
const editor = init_editor(editor_element, read_stage_data().checkpoint);
const show_console = init_console(by_test_id("game-console"), editor_element);

function apply_run({run, stage, checkpoint}) {
  if (run.status !== "in_progress") {
    // The server draws the victory or game-over screen for a finished run.
    window.location.reload();
    return;
  }
  show_lives(by_test_id("game-lives"), run.lives);
  if (stage) {
    show_stage(by_test_id("game-stage-readout"), stage.number);
    show_prompt(feed, stage.prompt);
    editor.open_stage(stage.number, checkpoint);
  } else {
    editor.reset(checkpoint);
  }
}

init_submit(
  by_test_id("game-submit"),
  by_test_id("game-verdict"),
  editor.get_code,
  show_console,
  apply_run,
);

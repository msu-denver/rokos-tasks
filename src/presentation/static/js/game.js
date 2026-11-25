/*
File: game.js
Description: Initializes the play page from the server-rendered stage.
Author(s): Tyler Black, Richard Hall
*/

import {init_console} from "./console.js";
import {init_editor} from "./editor.js";
import {init_feed} from "./feed.js";
import {init_submit} from "./submit.js";

init_feed(document.querySelector(".game-feed"));
const editor = document.querySelector(".game-editor");
const get_code = init_editor(editor);
const open_console = init_console(
  document.querySelector('[data-testid="game-console"]'),
  editor,
);
init_submit(
  document.querySelector('[data-testid="game-submit"]'),
  document.querySelector('[data-testid="game-verdict"]'),
  get_code,
  open_console,
);

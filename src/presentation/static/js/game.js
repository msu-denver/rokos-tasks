/*
File: game.js
Description: Initializes the play page from the server-rendered stage.
Author(s): Tyler Black
*/

import {init_editor} from "./editor.js";
import {init_feed} from "./feed.js";

init_feed(document.querySelector(".game-feed"));
init_editor(document.querySelector(".game-editor"));

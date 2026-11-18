/*
File: game.js
Description: Initializes the play page from the server-rendered stage.
Author(s): Tyler Black
*/

import {read_stage_data} from "./api.js";
import {init_editor} from "./editor.js";
import {init_feed} from "./feed.js";

const {starter_code} = read_stage_data();
init_feed(document.querySelector(".game-feed"));
init_editor(document.querySelector(".game-editor"), starter_code);

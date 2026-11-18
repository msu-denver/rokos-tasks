/*
File: game.js
Description: Initializes the play page from the server-rendered stage.
Author(s): Tyler Black
*/

import {readStageData} from "./api.js";
import {initEditor} from "./editor.js";
import {initFeed} from "./feed.js";

const {starter_code} = readStageData();
initFeed(document.querySelector(".game-feed"));
initEditor(document.querySelector(".game-editor"), starter_code);

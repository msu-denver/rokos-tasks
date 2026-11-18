/*
File: api.js
Description: Reads the public stage payload embedded in the play page.
Author(s): Tyler Black
*/

export function readStageData() {
  return JSON.parse(document.getElementById("stage-data").textContent);
}

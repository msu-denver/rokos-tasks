/*
File: api.js
Description: Reads the public stage payload embedded in the play page.
Author(s): Tyler Black
*/

export function read_stage_data() {
  return JSON.parse(document.getElementById("stage-data").textContent);
}

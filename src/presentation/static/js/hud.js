/*
File: hud.js
Description: Updates the top bar's lives and stage bar after a graded
    Submit (US7), so they match what the server now has for the run.
Author(s): Tyler Black
*/

export function show_lives(lives_element, lives) {
  const cells = lives_element.querySelectorAll(".game-life");
  cells.forEach((cell, index) => {
    cell.classList.toggle("game-life--full", index < lives);
  });
  lives_element.setAttribute(
    "aria-label", `${lives} of ${cells.length} lives`,
  );
}

export function show_stage(stage_bar, stage) {
  const cells = stage_bar.querySelectorAll(".stage-bar-cell");
  cells.forEach((cell, index) => {
    const number = index + 1;
    cell.classList.toggle("stage-bar-cell--done", number < stage);
    cell.classList.toggle("stage-bar-cell--current", number === stage);
  });
  const {tier} = stage_bar.dataset;
  stage_bar.setAttribute(
    "aria-label", `${tier}, stage ${stage} of ${cells.length}`,
  );
  document.title = document.title.replace(/^Stage \d+/, `Stage ${stage}`);
}

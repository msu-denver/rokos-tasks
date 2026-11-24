/*
File: submit.js
Description: Submit (US6): sends the editor's code to the grading route,
    keeps the button disabled while the Overlord plays the program, and
    shows the verdict or why there isn't one.
Author(s): Richard Hall
*/

const BUSY_LABEL = "The Overlord is playing your program…";
const FAILED_REQUEST = "Grading is unavailable. This submit didn't count.";

function part(verdict_panel, test_id) {
  return verdict_panel.querySelector(`[data-testid="${test_id}"]`);
}

function show_code(element, text) {
  element.textContent = text ?? "";
  element.hidden = !text;
}

function show_verdict(panel, verdict) {
  panel.classList.toggle("game-verdict--pass", verdict.passed);
  const heading = part(panel, "game-verdict-heading");
  heading.textContent = verdict.heading;
  heading.hidden = !verdict.heading;
  part(panel, "game-verdict-reason").textContent = verdict.reason ?? "";
  show_code(part(panel, "game-verdict-traceback"), verdict.traceback);
  show_code(part(panel, "game-verdict-frame"), verdict.last_frame);
  panel.hidden = false;
}

function show_message(panel, message) {
  show_verdict(panel, {passed: false, heading: "", reason: message});
}

async function post_code(button, code) {
  const {submitUrl, run, csrfToken} = button.dataset;
  const response = await fetch(submitUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    body: JSON.stringify({run_id: Number(run), code}),
  });
  const body = await response.json().catch(() => ({}));
  return {ok: response.ok, body};
}

export function init_submit(button, panel, get_code) {
  const idle_label = button.textContent;

  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = BUSY_LABEL;
    try {
      const {ok, body} = await post_code(button, get_code());
      if (ok) {
        show_verdict(panel, body.verdict);
      } else {
        show_message(panel, body.message ?? FAILED_REQUEST);
      }
    } catch {
      show_message(panel, FAILED_REQUEST);
    } finally {
      button.disabled = false;
      button.textContent = idle_label;
    }
  });
}

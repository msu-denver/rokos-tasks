/*
File: submit.js
Description: Submit (US6): sends the editor's code to the grading route,
    keeps the button disabled while the Overlord plays the program, and
    shows the verdict or why there isn't one, then hands the reply on so
    the page can apply the run's new state (US7).
Author(s): Richard Hall, Tyler Black
*/

const BUSY_LABEL = "The Overlord is playing your program…";
const FAILED_REQUEST = "Grading is unavailable. This submit didn't count.";
const CONFLICT = 409;

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
  show_code(part(panel, "game-verdict-frame"), verdict.last_screen);
  panel.hidden = false;
}

function show_message(panel, message) {
  show_verdict(panel, {passed: false, heading: "", reason: message});
}

async function post_attempt(button, {code, stage}) {
  const {submitUrl, run, csrfToken} = button.dataset;
  const response = await fetch(submitUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    body: JSON.stringify({run_id: Number(run), stage, code}),
  });
  const body = await response.json().catch(() => ({}));
  return {ok: response.ok, status: response.status, body};
}

// get_attempt returns {code, stage}: the editor's code and the stage the
// page shows. show_console runs after every verdict or message is shown:
// it opens a collapsed console and announces what's new. on_graded gets
// the whole reply after a verdict, to apply the run's new state (US7).
export function init_submit(
  button, panel, get_attempt, show_console, on_graded,
) {
  const idle_label = button.textContent;

  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = BUSY_LABEL;
    let reloading = false;
    try {
      const {ok, status, body} = await post_attempt(button, get_attempt());
      if (status === CONFLICT) {
        // The run moved on (another tab, or it ended): show where it is now.
        // Nothing was shown, so the console and button stay as they are.
        reloading = true;
        window.location.reload();
      } else if (ok) {
        show_verdict(panel, body.verdict);
        on_graded(body);
      } else {
        show_message(panel, body.message ?? FAILED_REQUEST);
      }
    } catch {
      show_message(panel, FAILED_REQUEST);
    } finally {
      if (!reloading) {
        button.disabled = false;
        button.textContent = idle_label;
        show_console();
      }
    }
  });
}

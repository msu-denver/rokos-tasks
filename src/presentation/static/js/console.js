
/*
File: console.js
Description: Compares and displays sample execution results.
Author(s): Steph Rivera
*/

// Matches OutputNormalizer in src/business/output_normalizer.py.
export function normalize_output(output) {
  const lines = output
    .split(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/)
    .map((line) => line.replace(
      /[\t-\r\x1c-\x20\x85\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/,
      "",
    ));

  while (lines.length && lines[lines.length - 1] === "") {
    lines.pop();
  }

  return lines.join("\n");
}


export function sample_passed(result) {
  return (
    result.error === "" &&
    normalize_output(result.output) ===
      normalize_output(result.expected_output)
  );
}

const MAX_DISPLAY_LENGTH = 10000;

function truncate_output(output) {
  if (output.length <= MAX_DISPLAY_LENGTH) {
    return output;
  }

  return output.slice(0, MAX_DISPLAY_LENGTH) +
    "\n… output truncated.";
}

function create_element(tag, test_id, text) {
  const element = document.createElement(tag);
  element.dataset.testid = test_id;
  element.textContent = text;
  return element;
}

function render_sample(result, index) {
  const number = index + 1;
  const prefix = `game-sample-${number}`;
  const passed = sample_passed(result);

  const container = document.createElement("section");
  container.className = "game-sample-result";
  container.dataset.testid = `${prefix}-result`;

  container.append(
    create_element("h3", `${prefix}-heading`, `Example ${number}`),
    create_element("span", `${prefix}-status`, passed ? "PASS" : "FAIL"),
  );

  container.append(
    create_element("h4", `${prefix}-expected-label`, "Expected output"),
    create_element("pre", `${prefix}-expected`, result.expected_output),
    create_element("h4", `${prefix}-actual-label`, "Actual output"),
    create_element("pre", `${prefix}-actual`, truncate_output(result.output)),
  );

  const error = [result.stderr, result.error].filter(Boolean).join("\n");

  if (error) {
    container.append(
      create_element("h4", `${prefix}-error-label`, "Error"),
      create_element("pre", `${prefix}-error`, truncate_output(error)),
    );
  }

  return container;
}


export function render_results(container, results) {
  const summary = container.querySelector(
    '[data-testid="game-sample-summary"]',
  );
  const sample_results = container.querySelector(
    ".game-sample-results",
  );

  sample_results.replaceChildren();

  let passed_count = 0;

  results.forEach((result, index) => {
    if (sample_passed(result)) {
      passed_count++;
    }

    sample_results.append(render_sample(result, index));
  });

  summary.textContent =
    `${passed_count} of ${results.length} samples passed`;

  container.hidden = false;
  container.scrollTop = 0;
}

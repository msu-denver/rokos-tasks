/*
File: pyodide_worker.js
Description: Executes Python sample programs in a Web Worker.
Author(s): Steph Rivera
*/

import {loadPyodide} from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";

let pyodide;

async function init_python() {
  try {
    pyodide = await loadPyodide();

    self.postMessage({
      type: "ready",
    });
  } catch (error) {
    self.postMessage({
      type: "load_error",
      error: error.message,
    });
  }
}

function run_sample(code, input_text) {
  const namespace = pyodide.toPy({
    player_code: code,
    sample_input: input_text,
  });

  try {
    const result = pyodide.runPython(`
import sys
import io
import traceback

original_stdin = sys.stdin
original_stdout = sys.stdout
original_stderr = sys.stderr

sys.stdin = io.StringIO(sample_input)
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()

error = ""

try:
    exec(compile(player_code, "main.py", "exec"), {
        "__name__": "__main__"
    })
except BaseException as exc:
    error = "".join(traceback.format_exception(
        type(exc), exc, exc.__traceback__.tb_next
    ))
finally:
    output = sys.stdout.getvalue()
    stderr = sys.stderr.getvalue()

    sys.stdin = original_stdin
    sys.stdout = original_stdout
    sys.stderr = original_stderr

{"output": output, "stderr": stderr, "error": error}
`, {globals: namespace});

    try {
      return result.toJs({
        dict_converter: Object.fromEntries,
      });
    } finally {
      result.destroy();
    }
  } finally {
    namespace.destroy();
  }
}


self.addEventListener("message", (event) => {
  const {type, code, sample} = event.data;

  if (type !== "run" || !pyodide) return;

  try {
    const result = run_sample(code, sample.input);

    self.postMessage({
      type: "result",
      result: {
        expected_output: sample.expected_output,
        ...result,
      },
    });
  } catch (error) {
    self.postMessage({
      type: "run_error",
      error: error.message,
    });
  }
});

init_python();

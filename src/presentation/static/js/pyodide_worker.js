/*
File: pyodide_worker.js
Description: Executes Python programs in a Web Worker, receives tick input
    through shared memory, and sends completed frames to the game page.
Author(s): Steph Rivera
*/

import {loadPyodide} from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";

const INPUT_STATE = 0;
const INPUT_LENGTH = 1;
const INPUT_START = 2;
const INPUT_EMPTY = 0;
const INPUT_READY = 1;
const MAX_INPUT_LENGTH = 64;
const MAX_OUTPUT_LENGTH = 10000;

let pyodide;
let used = false;
let tick_number = 0;

let pending_line = "";
let frame = "";
let has_frame_line = false;


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


function read_tick_input(shared) {
  // Ask the main thread for the next tick's input.
  self.postMessage({
    type: "input_request",
    tick: tick_number + 1,
  });

  // Block this worker until the main thread supplies input.
  while (Atomics.load(shared, INPUT_STATE) === INPUT_EMPTY) {
    Atomics.wait(shared, INPUT_STATE, INPUT_EMPTY);
  }

  const length = Atomics.load(shared, INPUT_LENGTH);

  if (
    Atomics.load(shared, INPUT_STATE) !== INPUT_READY ||
    length < 0 ||
    length > MAX_INPUT_LENGTH
  ) {
    throw new Error("Invalid tick input.");
  }

  const characters = shared.subarray(
    INPUT_START,
    INPUT_START + length,
  );

  const input = String.fromCodePoint(...characters);

  // Mark the buffer as available for the next tick.
  Atomics.store(shared, INPUT_STATE, INPUT_EMPTY);

  tick_number++;

  return input + "\n";
}


function create_stdin(shared) {
  const encoder = new TextEncoder();
  let pending = new Uint8Array(0);

  return (buffer) => {
    if (buffer.length === 0) {
      return 0;
    }

    if (pending.length === 0) {
      pending = encoder.encode(read_tick_input(shared));
    }

    const count = Math.min(buffer.length, pending.length);

    buffer.set(pending.subarray(0, count));
    pending = pending.subarray(count);

    return count;
  };
}


function truncate_output(output) {
  if (output.length <= MAX_OUTPUT_LENGTH) {
    return output;
  }

  return output.slice(0, MAX_OUTPUT_LENGTH) +
    "\n… output truncated.";
}


function send_frame() {
  self.postMessage({
    type: "frame",
    tick: tick_number,
    frame: truncate_output(frame),
  });

  frame = "";
  has_frame_line = false;
}


function process_line(line) {
  // Support both LF and CRLF line endings.
  if (line.endsWith("\r")) {
    line = line.slice(0, -1);
  }

  // A line containing only --- marks the end of a frame.
  if (line === "---") {
    send_frame();
    return;
  }

  const separator = has_frame_line ? "\n" : "";

  frame = (frame + separator + line).slice(
    0,
    MAX_OUTPUT_LENGTH + 1,
  );

  has_frame_line = true;
}


function process_output(output) {
  const lines = output.split("\n");

  lines.forEach((line, index) => {
    pending_line = (pending_line + line).slice(
      0,
      MAX_OUTPUT_LENGTH + 2,
    );

    // The final portion may be an incomplete line.
    if (index < lines.length - 1) {
      process_line(pending_line);
      pending_line = "";
    }
  });
}


function run_program(code, input_buffer) {
  if (
    !(input_buffer instanceof SharedArrayBuffer) ||
    input_buffer.byteLength !==
      (INPUT_START + MAX_INPUT_LENGTH) *
      Int32Array.BYTES_PER_ELEMENT
  ) {
    throw new Error("Invalid shared input buffer.");
  }

  const shared = new Int32Array(input_buffer);
  const stdout_decoder = new TextDecoder();
  const stderr_decoder = new TextDecoder();

  let stderr = "";

  tick_number = 0;
  pending_line = "";
  frame = "";
  has_frame_line = false;

  pyodide.setStdin({
    read: create_stdin(shared),
  });

  pyodide.setStdout({
    write(buffer) {
      process_output(
        stdout_decoder.decode(buffer, {stream: true}),
      );

      return buffer.length;
    },
  });

  pyodide.setStderr({
    write(buffer) {
      stderr = (
        stderr + stderr_decoder.decode(buffer, {stream: true})
      ).slice(0, MAX_OUTPUT_LENGTH + 1);

      return buffer.length;
    },
  });

  const namespace = pyodide.toPy({
    player_code: code,
  });

  try {
    const error = pyodide.runPython(`
import sys
import traceback

original_stdout = sys.stdout
original_stderr = sys.stderr

original_stdout.reconfigure(
    line_buffering=True,
    write_through=True
)
original_stderr.reconfigure(
    line_buffering=True,
    write_through=True
)

error = ""

try:
    exec(compile(player_code, "main.py", "exec"), {
        "__name__": "__main__"
    })
except SystemExit as exc:
    if exc.code not in (None, 0):
        error = "".join(traceback.format_exception(
            type(exc), exc, exc.__traceback__.tb_next
        ))
except BaseException as exc:
    error = "".join(traceback.format_exception(
        type(exc), exc, exc.__traceback__.tb_next
    ))
finally:
    original_stdout.flush()
    original_stderr.flush()

error
`, {globals: namespace});

    process_output(stdout_decoder.decode());

    stderr = (stderr + stderr_decoder.decode()).slice(
      0,
      MAX_OUTPUT_LENGTH + 1,
    );

    if (error) {
      self.postMessage({
        type: "run_error",
        error: truncate_output(error),
        stderr: truncate_output(stderr),
      });
    } else {
      self.postMessage({
        type: "finished",
        stderr: truncate_output(stderr),
      });
    }
  } finally {
    namespace.destroy();
  }
}


self.addEventListener("message", (event) => {
  const {type, code, input_buffer} = event.data;

  if (type !== "run" || !pyodide || used) {
    return;
  }

  // Each worker executes one program, preserving state between ticks.
  used = true;

  try {
    run_program(code, input_buffer);
  } catch (error) {
    self.postMessage({
      type: "run_error",
      error: error.message,
    });
  }
});


init_python();

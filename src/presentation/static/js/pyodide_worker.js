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

init_python();

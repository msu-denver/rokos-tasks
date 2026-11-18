/*
File: editor.js
Description: Loads the Python editor and saves drafts for both editor modes.
Author(s): Tyler Black
*/

const MONACO_BASE = "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/";
const SAVE_INTERVAL_MS = 1000;

function loadMonaco() {
  return new Promise((resolve, reject) => {
    // The blob starts the classic worker on the page's origin.
    const workerUrl = URL.createObjectURL(new Blob([
      `self.MonacoEnvironment = {baseUrl: ${JSON.stringify(MONACO_BASE)}};`,
      `importScripts(${JSON.stringify(`${MONACO_BASE}vs/base/worker/workerMain.js`)});`,
    ], {type: "text/javascript"}));
    window.MonacoEnvironment = {getWorkerUrl: () => workerUrl};

    const loader = document.createElement("script");
    loader.src = `${MONACO_BASE}vs/loader.js`;
    loader.onerror = reject;
    loader.onload = () => {
      window.require.config({paths: {vs: `${MONACO_BASE}vs`}});
      window.require(["vs/editor/editor.main"], () => resolve(window.monaco), reject);
    };
    document.head.append(loader);
  });
}

function initialCode(key, starterCode) {
  try {
    return localStorage.getItem(key) ?? starterCode;
  } catch {
    // Browsers can deny storage access for this origin.
    return starterCode;
  }
}

function autosave(key) {
  let pending = null;
  let timer = null;

  function flush() {
    clearTimeout(timer);
    timer = null;
    if (pending === null) return;
    try {
      localStorage.setItem(key, pending);
    } catch {
      // Keep editing available if storage is blocked or full.
    }
    pending = null;
  }

  window.addEventListener("pagehide", flush);
  return (code) => {
    pending = code;
    timer ??= setTimeout(flush, SAVE_INTERVAL_MS);
  };
}

function editorOptions(monaco, value) {
  const styles = getComputedStyle(document.documentElement);
  const token = (name) => styles.getPropertyValue(name).trim();
  monaco.editor.defineTheme("rokos", {
    base: "vs-dark",
    inherit: true,
    rules: [
      {token: "keyword", foreground: token("--cyan").slice(1)},
      {token: "number", foreground: token("--cyan").slice(1)},
      {token: "string", foreground: token("--yellow").slice(1)},
      {token: "comment", foreground: token("--muted").slice(1)},
    ],
    colors: {
      "editor.background": token("--surface"),
      "editor.foreground": token("--ink"),
      "editor.lineHighlightBackground": token("--surface-raised"),
      "editorCursor.foreground": token("--cyan"),
      "editorLineNumber.foreground": token("--muted"),
      "editorLineNumber.activeForeground": token("--ink-strong"),
    },
  });
  return {
    value,
    language: "python",
    theme: "rokos",
    ariaLabel: "Python editor",
    fontFamily: token("--font-mono"),
    fontSize: parseFloat(token("--text-14")),
    cursorBlinking: matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "solid" : "blink",
    tabSize: 4,
    insertSpaces: true,
    detectIndentation: false,
    automaticLayout: true,
    minimap: {enabled: false},
    scrollBeyondLastLine: false,
  };
}

export async function initEditor(container, starterCode) {
  const [textarea, host] = container.children;
  const {run, stage} = container.dataset;
  const key = `rokos:run:${run}:stage:${stage}`;
  const save = autosave(key);
  textarea.value = initialCode(key, starterCode);
  textarea.addEventListener("input", () => save(textarea.value));

  try {
    const monaco = await loadMonaco();
    host.hidden = false;
    const editor = monaco.editor.create(host, editorOptions(monaco, textarea.value));
    editor.onDidChangeModelContent(() => save(editor.getValue()));
    if (document.activeElement === textarea) {
      const model = editor.getModel();
      editor.setSelection(monaco.Selection.fromPositions(
        model.getPositionAt(textarea.selectionStart),
        model.getPositionAt(textarea.selectionEnd),
      ));
      editor.focus();
    }
    textarea.hidden = true;
  } catch (error) {
    host.hidden = true;
    console.warn("Monaco is unavailable", error);
  }
}

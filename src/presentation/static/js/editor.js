/*
File: editor.js
Description: Loads the Python editor, saves drafts for both editor modes,
    and loads checkpoint code when a stage opens or resets (US7).
Author(s): Tyler Black, Richard Hall
*/

const MONACO_BASE = "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/";
const SAVE_INTERVAL_MS = 1000;
const PYTHON_BUILTINS = [
  "abs", "all", "any", "bin", "bool", "bytes", "chr", "dict", "divmod",
  "enumerate", "filter", "float", "format", "frozenset", "hex", "input",
  "int", "isinstance", "iter", "len", "list", "map", "max", "min", "next",
  "oct", "ord", "pow", "print", "range", "repr", "reversed", "round", "set",
  "slice", "sorted", "str", "sum", "tuple", "type", "zip",
];

function load_monaco() {
  return new Promise((resolve, reject) => {
    // The blob starts the classic worker on the page's origin.
    const worker_url = URL.createObjectURL(new Blob([
      `self.MonacoEnvironment = {baseUrl: ${JSON.stringify(MONACO_BASE)}};`,
      `importScripts(${JSON.stringify(`${MONACO_BASE}vs/base/worker/workerMain.js`)});`,
    ], {type: "text/javascript"}));
    window.MonacoEnvironment = {getWorkerUrl: () => worker_url};

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

function draft_key(run, stage) {
  return `rokos:run:${run}:stage:${stage}`;
}

// A saved draft wins over the checkpoint. Every line in the editor is the
// player's own: their draft, their last passing code, or nothing.
function initial_code(key, checkpoint) {
  try {
    return localStorage.getItem(key) ?? checkpoint ?? "";
  } catch {
    // Browsers can deny storage access for this origin.
    return checkpoint ?? "";
  }
}

function clear_draft(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    // Nothing to clear if storage is blocked.
  }
}

// Saves to whichever stage's key is current. `discard` drops an unsaved
// edit, so a passed or reset stage keeps no draft.
function autosave(initial_key) {
  let key = initial_key;
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
  return {
    save(code) {
      pending = code;
      timer ??= setTimeout(flush, SAVE_INTERVAL_MS);
    },
    discard() {
      clearTimeout(timer);
      timer = null;
      pending = null;
    },
    get key() {
      return key;
    },
    set key(next) {
      key = next;
    },
  };
}

function register_python_completions(monaco) {
  // Match Monaco's document-word provider priority so both sets are offered.
  return monaco.languages.registerCompletionItemProvider("*", {
    provideCompletionItems(model, position) {
      if (model.getLanguageId() !== "python") return;
      const {word, startColumn, endColumn} = model.getWordUntilPosition(position);
      const line = position.lineNumber;
      const range = new monaco.Range(line, startColumn, line, endColumn);
      const suggestions = PYTHON_BUILTINS
        .filter((name) => name.startsWith(word) && name !== word)
        .map((name) => ({
          label: name,
          kind: monaco.languages.CompletionItemKind.Function,
          insertText: name,
          range,
        }));
      return {suggestions};
    },
  });
}

function editor_options(monaco, value) {
  const styles = getComputedStyle(document.documentElement);
  const token = (name) => styles.getPropertyValue(name).trim();
  const ink = token("--ink");
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
      "editor.foreground": ink,
      "editor.lineHighlightBackground": token("--surface-raised"),
      "editorCursor.foreground": token("--cyan"),
      "editorLineNumber.foreground": token("--muted"),
      "editorLineNumber.activeForeground": token("--ink-strong"),
      "editorSuggestWidget.background": token("--surface"),
      "editorSuggestWidget.border": token("--muted"),
      "editorSuggestWidget.foreground": ink,
      "editorSuggestWidget.highlightForeground": token("--cyan"),
      "editorSuggestWidget.selectedBackground": token("--surface-raised"),
      "symbolIcon.functionForeground": token("--cyan"),
      "symbolIcon.textForeground": token("--muted"),
      "editorBracketHighlight.foreground1": ink,
      "editorBracketHighlight.foreground2": ink,
      "editorBracketHighlight.foreground3": ink,
      "editorBracketHighlight.foreground4": ink,
      "editorBracketHighlight.foreground5": ink,
      "editorBracketHighlight.foreground6": ink,
      "editorBracketHighlight.unexpectedBracket.foreground": token("--magenta"),
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
    autoClosingQuotes: "languageDefined",
    tabCompletion: "on",
    wordBasedSuggestions: "currentDocument",
    automaticLayout: true,
    minimap: {enabled: false},
    scrollBeyondLastLine: false,
  };
}

// Returns the editor's controls, which work whichever editor is showing:
// the textarea until Monaco loads (or if it never does).
//   get_code(): the code right now.
//   open_stage(stage, checkpoint): after a pass, clear the passed stage's
//     draft and load the new stage's draft or the checkpoint.
//   reset(checkpoint): after a fail, clear the stage's draft and go back
//     to the checkpoint (empty on Stage 1).
//   finish(): after the last stage, clear its draft.
//   stage(): the stage the editor is on.
export function init_editor(container, checkpoint) {
  const [textarea, host] = container.children;
  const {run} = container.dataset;
  const drafts = autosave(draft_key(run, container.dataset.stage));
  // Code the page puts in the editor isn't an edit, so it isn't saved.
  let loading = false;
  const save = (code) => {
    if (!loading) drafts.save(code);
  };
  textarea.value = initial_code(drafts.key, checkpoint);
  textarea.addEventListener("input", () => save(textarea.value));

  let editor = null;
  start_monaco(textarea, host, save).then((created) => {
    editor = created;
  });

  function show(code) {
    loading = true;
    textarea.value = code;
    editor?.setValue(code);
    loading = false;
  }

  function forget_stage() {
    drafts.discard();
    clear_draft(drafts.key);
  }

  return {
    get_code: () => (editor ? editor.getValue() : textarea.value),
    open_stage(stage, next_checkpoint) {
      forget_stage();
      container.dataset.stage = stage;
      drafts.key = draft_key(run, stage);
      show(initial_code(drafts.key, next_checkpoint));
    },
    reset(last_checkpoint) {
      forget_stage();
      show(last_checkpoint ?? "");
    },
    finish: forget_stage,
    stage: () => Number(container.dataset.stage),
  };
}

async function start_monaco(textarea, host, save) {
  try {
    const monaco = await load_monaco();
    host.hidden = false;
    const editor = monaco.editor.create(host, editor_options(monaco, textarea.value));
    const completions = register_python_completions(monaco);
    editor.onDidDispose(() => completions.dispose());
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
    return editor;
  } catch (error) {
    host.hidden = true;
    console.warn("Monaco is unavailable", error);
    return null;
  }
}

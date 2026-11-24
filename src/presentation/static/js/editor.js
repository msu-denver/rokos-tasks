/*
File: editor.js
Description: Loads the Python editor and saves drafts for both editor modes.
Author(s): Tyler Black
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

// The editor starts empty: every line in it is the player's own.
function initial_code(key) {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    // Browsers can deny storage access for this origin.
    return "";
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

export async function init_editor(container) {
  const [textarea, host] = container.children;
  const {run, stage} = container.dataset;
  const key = `rokos:run:${run}:stage:${stage}`;
  const save = autosave(key);
  textarea.value = initial_code(key);
  textarea.addEventListener("input", () => save(textarea.value));

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

    return {
      get_code: () => editor.getValue(),
    };
  } catch (error) {
    host.hidden = true;
    console.warn("Monaco is unavailable", error);

    return {
      get_code: () => textarea.value,
    };
  }
}

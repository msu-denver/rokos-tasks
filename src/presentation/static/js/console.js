/*
File: console.js
Description: The console under the editor, like an IDE's terminal panel:
    its top edge resizes it against the editor (mouse or arrow keys), its
    bar collapses and expands it, new output opens it, and its height and
    open state are remembered across reloads.
Author(s): Tyler Black
*/

const STORAGE_KEY = "rokos:console";

function load_layout() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return {
      expanded: saved?.expanded === true,
      size: Number.isFinite(saved?.size) ? saved.size : null,
    };
  } catch {
    // Storage can be blocked, or hold something that isn't ours.
    return {expanded: false, size: null};
  }
}

function save_layout(layout) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
  } catch {
    // The console still works; it just won't be remembered.
  }
}

function token_px(name) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name);
  return parseFloat(value);
}

// How far the console sticks out past the bottom of the editor window's
// content box (after the window shrinks, say).
function overflow({panel, root}) {
  const panel_style = getComputedStyle(panel);
  const content_bottom = panel.getBoundingClientRect().bottom
    - parseFloat(panel_style.paddingBlockEnd)
    - parseFloat(panel_style.borderBlockEndWidth);
  return Math.max(0, root.getBoundingClientRect().bottom - content_bottom);
}

// Desktop: the console and editor share the window's height, so the
// console may grow until the editor reaches its minimum. Stacked layout:
// the page scrolls and the CSS max-block-size caps the console.
function size_limits(parts) {
  const {editor, body} = parts;
  const body_style = getComputedStyle(body);
  const min = parseFloat(body_style.minBlockSize);
  let max = parseFloat(body_style.maxBlockSize);
  if (Number.isNaN(max)) {
    const shared = editor.offsetHeight + body.offsetHeight - overflow(parts);
    max = shared - parseFloat(getComputedStyle(editor).minBlockSize);
  }
  return {min, max: Math.max(min, max)};
}

export function init_console(root, editor) {
  const parts = {
    root,
    panel: root.closest(".game-editor-panel"),
    editor,
    body: root.querySelector('[data-testid="game-console-body"]'),
  };
  const handle = root.querySelector('[data-testid="game-console-handle"]');
  const toggle = root.querySelector('[data-testid="game-console-toggle"]');
  const layout = load_layout();

  // Shows the preferred size, clamped to the space there is right now.
  function apply_size() {
    if (!layout.expanded) return;
    const {body} = parts;
    if (layout.size === null) body.style.removeProperty("--console-size");
    const wanted = layout.size ?? body.offsetHeight;
    const {min, max} = size_limits(parts);
    const size = Math.round(Math.min(Math.max(wanted, min), max));
    body.style.setProperty("--console-size", `${size}px`);
    handle.setAttribute("aria-valuemin", Math.round(min));
    handle.setAttribute("aria-valuemax", Math.round(max));
    handle.setAttribute("aria-valuenow", size);
    return size;
  }

  function resize(size) {
    layout.size = size;
    layout.size = apply_size();
  }

  function set_expanded(expanded) {
    layout.expanded = expanded;
    toggle.setAttribute("aria-expanded", String(expanded));
    parts.body.hidden = !expanded;
    handle.hidden = !expanded;
    apply_size();
  }

  toggle.addEventListener("click", () => {
    set_expanded(!layout.expanded);
    save_layout(layout);
  });

  handle.addEventListener("keydown", (event) => {
    const current = parts.body.offsetHeight;
    const step = token_px("--space-4");
    const page = token_px("--grid-size");
    const sizes = {
      ArrowUp: current + step,
      ArrowDown: current - step,
      PageUp: current + page,
      PageDown: current - page,
      Home: 0,
      End: Infinity,
    };
    if (!(event.key in sizes)) return;
    event.preventDefault();
    resize(sizes[event.key]);
    save_layout(layout);
  });

  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    const start_y = event.clientY;
    const start_size = parts.body.offsetHeight;
    root.classList.add("game-console--resizing");

    const move = (moved) => resize(start_size + start_y - moved.clientY);
    const stop = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", stop);
      handle.removeEventListener("pointercancel", stop);
      root.classList.remove("game-console--resizing");
      save_layout(layout);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", stop);
    handle.addEventListener("pointercancel", stop);
  });

  window.addEventListener("resize", apply_size);
  set_expanded(layout.expanded);

  // Called before new output is shown, so the live region is visible
  // when its text changes and screen readers announce it.
  return () => {
    if (layout.expanded) return;
    set_expanded(true);
    save_layout(layout);
  };
}

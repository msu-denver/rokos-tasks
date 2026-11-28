/*
File: console.js
Description: The console under the editor, like an IDE's terminal panel:
    its top edge resizes it against the editor (mouse or arrow keys), its
    bar collapses and expands it, new output opens it and is announced,
    and its height and open state are remembered across reloads.
Author(s): Tyler Black, Steph Rivera
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

// The console and editor share a fixed height in both layouts (see
// components.css), so the console may grow until the editor reaches its
// minimum.
function size_limits(parts) {
  const {editor, body} = parts;
  const min = parseFloat(getComputedStyle(body).minBlockSize);
  const shared = editor.offsetHeight + body.offsetHeight - overflow(parts);
  const max = shared - parseFloat(getComputedStyle(editor).minBlockSize);
  return {min, max: Math.max(min, max)};
}

// The verdict's heading and reason, read as one line.
function summary(root) {
  const parts = ["game-verdict-heading", "game-verdict-reason"]
    .map((test_id) => root.querySelector(`[data-testid="${test_id}"]`))
    .filter((element) => !element.hidden && element.textContent)
    .map((element) => element.textContent);
  return parts.join(". ");
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
  const status = root.querySelector('[data-testid="game-console-status"]');
  const layout = load_layout();
  let drag = null;

  // Shows the preferred size, clamped to the space there is right now.
  function apply_size() {
    if (!layout.expanded) return;
    const {panel, body} = parts;
    if (layout.size === null) panel.style.removeProperty("--console-size");
    const wanted = layout.size ?? body.offsetHeight;
    const {min, max} = size_limits(parts);
    const size = Math.round(Math.min(Math.max(wanted, min), max));
    panel.style.setProperty("--console-size", `${size}px`);
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
    // Closed, the console gives all of its height back to the editor.
    if (!expanded) parts.panel.style.removeProperty("--console-size");
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

  // One pointer drives a drag; a second finger is ignored. Capture ends
  // on pointerup and pointercancel too, so lostpointercapture ends it.
  handle.addEventListener("pointerdown", (event) => {
    if (drag || event.button !== 0) return;
    event.preventDefault();
    drag = {
      pointer: event.pointerId,
      start_y: event.clientY,
      start_size: parts.body.offsetHeight,
    };
    handle.setPointerCapture(event.pointerId);
    root.classList.add("game-console--resizing");
  });

  handle.addEventListener("pointermove", (event) => {
    if (drag?.pointer !== event.pointerId) return;
    resize(drag.start_size + drag.start_y - event.clientY);
  });

  handle.addEventListener("lostpointercapture", (event) => {
    if (drag?.pointer !== event.pointerId) return;
    drag = null;
    root.classList.remove("game-console--resizing");
    save_layout(layout);
  });

  window.addEventListener("resize", apply_size);
  set_expanded(layout.expanded);

  // Opens a collapsed console and announces new output.
  // Without a custom message, announces the Submit verdict.
  return (message = null) => {
    if (!layout.expanded) {
      set_expanded(true);
      save_layout(layout);
    }
    status.textContent = "";
    requestAnimationFrame(() => {
      status.textContent = message ?? summary(root);
    });
  };
}

/*
File: play.js
Description: Manages browser-based Python execution, input styles,
    turn scheduling, worker lifecycle, and timeout recovery.
Author(s): Steph Rivera
*/

const TICK_INTERVAL_MS = 100;
const TICK_TIMEOUT_MS = 1000;

const INPUT_STATE = 0;
const INPUT_LENGTH = 1;
const INPUT_START = 2;
const INPUT_READY = 1;
const MAX_INPUT_LENGTH = 64;

const INPUT_STYLES = ["none", "lines", "keys"];
const TIMEOUT_MESSAGE =
  "Your program took more than 1 second to answer and was stopped. " +
  "Check for an infinite loop.";

export function create_player({
  on_state = () => {},
  on_frame = () => {},
  on_input = () => {},
  on_error = () => {},
  on_timeout = () => {},
  on_finish = () => {},
} = {}) {
  let worker = null;
  let worker_url = null;
  let state = "idle";
  let shared = null;
  let input_style = null;
  let keys = [];
  let tick_timer = null;
  let timeout_id = null;
  let last_tick_at = null;
  let current_tick = 0;
  let phase = null;

  function set_state(value) {
    state = value;
    on_state(value);
  }

  function clear_timeout() {
    clearTimeout(timeout_id);
    timeout_id = null;
  }

  function clear_timers() {
    clearTimeout(tick_timer);
    tick_timer = null;
    clear_timeout();
  }

  function terminate_worker() {
    clear_timers();
    worker?.terminate();
    worker = null;
    shared = null;
    input_style = null;
    keys = [];
    phase = null;
  }

  function restart_worker() {
    terminate_worker();
    set_state("restarting");
    start_worker();
  }

  function handle_timeout() {
    if (state !== "running" || phase !== "executing") return;

    restart_worker();
    on_timeout(TIMEOUT_MESSAGE);
  }

  function start_timeout() {
    clear_timeout();
    timeout_id = setTimeout(handle_timeout, TICK_TIMEOUT_MS);
  }

  function send_input(input) {
    if (
      state !== "running" ||
      phase !== "waiting_for_input" ||
      input.length > MAX_INPUT_LENGTH
    ) {
      return false;
    }

    Atomics.store(shared, INPUT_LENGTH, input.length);
    input.forEach((character, index) => {
      Atomics.store(shared, INPUT_START + index, character.codePointAt(0));
    });

    current_tick++;
    last_tick_at = performance.now();
    phase = "executing";
    start_timeout();

    Atomics.store(shared, INPUT_STATE, INPUT_READY);
    Atomics.notify(shared, INPUT_STATE);
    return true;
  }

  function send_tick() {
    tick_timer = null;
    if (
      input_style !== "keys" ||
      phase !== "waiting_for_input"
    ) return;

    send_input(keys.splice(0, MAX_INPUT_LENGTH));
  }

  function schedule_tick() {
    if (
      input_style !== "keys" ||
      phase !== "waiting_for_input"
    ) return;

    const delay = last_tick_at === null
      ? 0
      : Math.max(
        0,
        TICK_INTERVAL_MS - (performance.now() - last_tick_at),
      );

    tick_timer = setTimeout(send_tick, delay);
  }

  function submit_line(line) {
    if (
      input_style !== "lines" ||
      typeof line !== "string" ||
      /[\r\n]/.test(line)
    ) return false;

    return send_input(Array.from(line));
  }

  function handle_failure(error) {
    if (state === "running") {
      on_error(error);
      restart_worker();
      return;
    }

    terminate_worker();
    set_state("unavailable");
    on_error(error);
  }

  function handle_input_request(screen, tick) {
    if (
      phase !== "executing" ||
      tick !== current_tick + 1
    ) return;

    // Waiting for a player or the next turn is not execution time.
    clear_timeout();
    phase = "waiting_for_input";
    on_frame(screen, current_tick);

    if (input_style === "keys") {
      schedule_tick();
    } else if (input_style === "lines") {
      on_input();
    } else {
      handle_failure("This stage does not accept input.");
    }
  }

  function handle_completion({type, screen, stderr, error}) {
    clear_timeout();
    if (typeof screen === "string") {
      on_frame(screen, current_tick);
    }

    if (type === "run_error") {
      handle_failure([stderr, error].filter(Boolean).join("\n"));
    } else {
      restart_worker();
      on_finish(stderr);
    }
  }

  function handle_message(message) {
    const {type, error, screen, tick} = message;

    if (type === "ready") {
      set_state("ready");
      return;
    }
    if (type === "load_error") {
      handle_failure(error);
      return;
    }
    if (state !== "running") return;

    if (type === "input_request") {
      handle_input_request(screen, tick);
    } else if (type === "finished" || type === "run_error") {
      handle_completion(message);
    }
  }

  function start_worker() {
    try {
      const current_worker = new Worker(worker_url, {type: "module"});
      worker = current_worker;

      current_worker.addEventListener("message", (event) => {
        if (worker !== current_worker) return;
        handle_message(event.data);
      });
      current_worker.addEventListener("error", (event) => {
        if (worker !== current_worker) return;
        handle_failure(
          event.message || "Python encountered an unexpected error.",
        );
      });
    } catch (error) {
      handle_failure(error.message);
    }
  }

  async function init() {
    if (state !== "idle") return;
    set_state("loading");

    try {
      if (
        !globalThis.crossOriginIsolated ||
        typeof SharedArrayBuffer === "undefined"
      ) throw new Error("Shared memory is unavailable.");

      // Cache the worker source so restarting needs no app-server fetch.
      const response = await fetch(
        new URL("./pyodide_worker.js", import.meta.url),
      );
      if (!response.ok) throw new Error("Unable to load Python worker.");

      const source = await response.text();
      const blob = new Blob([source], {type: "text/javascript"});
      worker_url = URL.createObjectURL(blob);
      start_worker();
    } catch (error) {
      handle_failure(error.message);
    }
  }

  function run(code, style) {
    if (state !== "ready" || !INPUT_STYLES.includes(style)) return false;

    const input_buffer = new SharedArrayBuffer(
      (INPUT_START + MAX_INPUT_LENGTH) * Int32Array.BYTES_PER_ELEMENT,
    );
    shared = new Int32Array(input_buffer);
    input_style = style;
    keys = [];
    current_tick = 0;
    last_tick_at = null;
    phase = "executing";

    set_state("running");
    start_timeout();
    worker.postMessage({type: "run", code, input_buffer});
    return true;
  }

  function stop() {
    if (state !== "running") return;
    restart_worker();
  }

  function queue_key(key) {
    if (
      state !== "running" ||
      input_style !== "keys" ||
      keys.length >= MAX_INPUT_LENGTH ||
      typeof key !== "string"
    ) return;

    // Accept printable characters, including ordinary spaces.
    if (key === " " || /^[^\p{C}\p{Z}]$/u.test(key)) {
      keys.push(key);
    }
  }

  return {init, run, stop, queue_key, submit_line};
}

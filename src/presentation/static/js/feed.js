/*
File: feed.js
Description: Styles exact prompt values, marks scrolled feed content, and
    shows the next stage's prompt after a pass (US7).
Author(s): Tyler Black
*/

function format_message(message) {
  const parts = message.textContent.split(/`([^`\n]+)`/);
  message.replaceChildren(...parts.map((part, index) => {
    if (index % 2 === 0) return part;
    const code = document.createElement("code");
    code.textContent = part;
    return code;
  }));
}

export function init_feed(feed) {
  for (const message of feed.children) format_message(message);

  feed.addEventListener("scroll", () => {
    feed.classList.toggle("game-feed--scrolled", feed.scrollTop > 0);
  }, {passive: true});
}

// A new stage starts a new feed, the same as loading the page fresh.
export function show_prompt(feed, text) {
  const prompt = document.createElement("p");
  prompt.dataset.testid = "game-prompt";
  prompt.textContent = text;
  format_message(prompt);
  feed.replaceChildren(prompt);
  feed.scrollTop = 0;
  feed.classList.remove("game-feed--scrolled");
}

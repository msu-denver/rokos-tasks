/*
File: feed.js
Description: Styles exact prompt values and marks scrolled feed content.
Author(s): Tyler Black
*/

export function initFeed(feed) {
  for (const message of feed.children) {
    const parts = message.textContent.split(/`([^`\n]+)`/);
    message.replaceChildren(...parts.map((part, index) => {
      if (index % 2 === 0) return part;
      const code = document.createElement("code");
      code.textContent = part;
      return code;
    }));
  }

  feed.addEventListener("scroll", () => {
    feed.classList.toggle("game-feed--scrolled", feed.scrollTop > 0);
  }, {passive: true});
}

let dialogSequence = 0;
const dialogOpeners = new WeakMap();

function nextDialogId() {
  dialogSequence += 1;
  return `finance-dialog-title-${dialogSequence}`;
}

function connected(element) {
  return element instanceof HTMLElement && element.isConnected;
}

export function showAccessibleDialog(dialog, { opener = document.activeElement, initialFocus = null } = {}) {
  if (!(dialog instanceof HTMLDialogElement)) throw new TypeError("A dialog element is required.");

  const heading = dialog.querySelector("h1, h2, h3");
  if (!dialog.hasAttribute("aria-label") && !dialog.hasAttribute("aria-labelledby") && heading) {
    if (!heading.id) heading.id = nextDialogId();
    dialog.setAttribute("aria-labelledby", heading.id);
  }

  const description = dialog.querySelector("p");
  if (!dialog.hasAttribute("aria-describedby") && description) {
    if (!description.id) description.id = `${nextDialogId()}-description`;
    dialog.setAttribute("aria-describedby", description.id);
  }

  if (!dialog.hasAttribute("aria-label") && !dialog.hasAttribute("aria-labelledby")) {
    throw new TypeError("An accessible dialog name is required.");
  }

  dialog.setAttribute("aria-modal", "true");
  dialogOpeners.set(dialog, opener);

  dialog.addEventListener("close", () => {
    queueMicrotask(() => {
      if (connected(opener)) opener.focus({ preventScroll: true });
    });
  }, { once: true });

  dialog.showModal();

  queueMicrotask(() => {
    const target = typeof initialFocus === "function" ? initialFocus(dialog) : initialFocus;
    if (connected(target)) {
      target.focus({ preventScroll: true });
      return;
    }
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
  });
}

export function getDialogOpener(dialog) {
  return dialogOpeners.get(dialog) ?? null;
}

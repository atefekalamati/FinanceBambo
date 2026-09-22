import assert from "node:assert/strict";
import test from "node:test";

import { installDom } from "../helpers/dom.js";

installDom();

const { createInvoicesEntry } =
  await import("../../src/features/finance-home/invoices-entry.js");

test("every invoice entry action opens the invoice page", () => {
  const entry = createInvoicesEntry();
  const links = entry.querySelectorAll("a");
  assert.equal(links.length, 5, "three chips and two footer actions are links");
  assert.ok(links.every((link) => link.href === "#finance/invoices"));
  assert.equal(entry.querySelectorAll("li").length, 3);
});

test("a host-provided invoice route is shared by every action", () => {
  const entry = createInvoicesEntry({ href: "#finance/invoices?from=overview" });
  assert.ok(entry.querySelectorAll("a")
    .every((link) => link.href === "#finance/invoices?from=overview"));
});

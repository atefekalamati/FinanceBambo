import test from "node:test";
import assert from "node:assert/strict";

import { actorLabel, NO_ACTOR } from "../../src/shared/formatters/actor.js";

const ADMIN = "53a1ac1b-d87f-4125-9ba9-a7d64166af88";

test("a name the host knows is what the reader sees", () => {
  assert.equal(actorLabel("مدیر سیستم", ADMIN), "مدیر سیستم");
});

test("without a name the id is shown, not a placeholder", () => {
  // The id is the one identifying fact the record holds. A reader who cannot be given a
  // name can still copy it, match it on another page, or hand it to someone who can resolve
  // it -- «کاربر نامشخص» would throw that away to look tidier.
  assert.equal(actorLabel(null, ADMIN), ADMIN);
  assert.equal(actorLabel(undefined, ADMIN), ADMIN);
});

test("a blank or whitespace name counts as no name", () => {
  assert.equal(actorLabel("", ADMIN), ADMIN);
  assert.equal(actorLabel("   ", ADMIN), ADMIN);
});

test("a name is trimmed rather than shown with the host's padding", () => {
  assert.equal(actorLabel("  مدیر سیستم  ", ADMIN), "مدیر سیستم");
});

test("a record with no actor at all says so, because there is nothing to fall back to", () => {
  // An unattended import has no importer. That is a different thing from an importer whose
  // name is unknown, and the two must not read the same.
  assert.equal(actorLabel(null, null), NO_ACTOR);
  assert.equal(actorLabel(null, ""), NO_ACTOR);
  assert.equal(actorLabel(null, undefined), NO_ACTOR);
});

test("callers may name the absent case in their own words", () => {
  assert.equal(actorLabel(null, null, "تأیید نشده"), "تأیید نشده");
});

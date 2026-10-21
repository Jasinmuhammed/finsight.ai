import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const authForm = readFileSync(
  new URL("../src/components/auth-form.tsx", import.meta.url),
  "utf8",
);

test("login sends the expected credentials to the versioned auth endpoint", () => {
  assert.match(authForm, /NEXT_PUBLIC_API_BASE_URL/);
  assert.match(authForm, /\/auth\/\$\{isRegistration \? "register" : "login"\}/);
  assert.match(authForm, /credentials:\s*"include"/);
  assert.match(authForm, /JSON\.stringify\(\{\s*email,\s*password\s*\}\)/);
});

test("HTTP authentication errors do not claim the API is unavailable", () => {
  assert.match(authForm, /if \(!response\.ok\)[\s\S]*?throw new Error\(detail \|\| `Request failed/);
  assert.match(authForm, /Unable to connect to the API\. Check that the API is running/);
  assert.match(authForm, /setError\(\s*submitError instanceof Error\s*\?\s*submitError\.message/);
  assert.doesNotMatch(authForm, /submitError\.message\} Check that the API is running/);
});

test("successful login redirects and refreshes the authenticated app shell", () => {
  assert.match(authForm, /router\.replace\("\/"\)/);
  assert.match(authForm, /router\.refresh\(\)/);
});

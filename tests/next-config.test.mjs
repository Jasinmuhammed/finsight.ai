import assert from "node:assert/strict";
import { test } from "node:test";

import nextConfig from "../next.config.mjs";

test("allows the local hosts used to access the Next.js development server", () => {
  assert.deepEqual(nextConfig.allowedDevOrigins, ["localhost", "127.0.0.1"]);
});

// Starts the real backend (which also serves the built frontend) on an isolated data dir.
// Cross-platform (Windows + Linux): no shell env syntax needed.
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = mkdtempSync(join(tmpdir(), "cfs-e2e-"));
const child = spawn("uv", ["run", "cfs"], {
  cwd: join(here, "..", "..", "backend"),
  env: {
    ...process.env,
    CFS_DATA_DIR: dataDir,
    CFS_PORT: process.env.CFS_PORT || "8766",
    CFS_FAKE_PROVIDER: "e2e", // scripted AI answers; never calls Gemini
  },
  stdio: "inherit",
  shell: process.platform === "win32",
});
const stop = () => child.kill();
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
child.on("exit", (code) => process.exit(code ?? 0));

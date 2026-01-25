#!/usr/bin/env bun

const scriptName = "db-migrate";
console.log(`[${scriptName}] running alembic migrations`);

const proc = Bun.spawn({
  cmd: ["alembic", "upgrade", "head"],
  cwd: "services/api",
  stdout: "inherit",
  stderr: "inherit",
  stdin: "inherit",
});

const exitCode = await proc.exited;
if (exitCode !== 0) {
  console.error(`[${scriptName}] failed with exit code ${exitCode}`);
  process.exit(exitCode);
}

console.log(`[${scriptName}] complete`);

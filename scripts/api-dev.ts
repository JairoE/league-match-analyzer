#!/usr/bin/env bun

const scriptName = "api-dev";
console.log(`[${scriptName}] starting FastAPI with reload`);

const proc = Bun.spawn({
  cmd: ["uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
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

#!/usr/bin/env bun

const scriptName = "llm-dev";
console.log(`[${scriptName}] starting LLM worker`);

const proc = Bun.spawn({
  cmd: ["python", "main.py"],
  cwd: "services/llm",
  stdout: "inherit",
  stderr: "inherit",
  stdin: "inherit",
});

const exitCode = await proc.exited;
if (exitCode !== 0) {
  console.error(`[${scriptName}] failed with exit code ${exitCode}`);
  process.exit(exitCode);
}

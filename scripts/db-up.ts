#!/usr/bin/env bun

const scriptName = "db-up";
console.log(`[${scriptName}] starting docker compose`);

const proc = Bun.spawn({
  cmd: ["docker", "compose", "-f", "infra/compose/docker-compose.yml", "up", "-d"],
  stdout: "inherit",
  stderr: "inherit",
  stdin: "inherit",
});

const exitCode = await proc.exited;
if (exitCode !== 0) {
  console.error(`[${scriptName}] failed with exit code ${exitCode}`);
  process.exit(exitCode);
}

console.log(`[${scriptName}] ready`);

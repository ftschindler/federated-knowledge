#!/usr/bin/env node
// check-skill-frontmatter.mjs — commit-time guard.
// Every committed SKILL.md must be discoverable by skills.sh (`npx skills add`),
// which requires YAML frontmatter with a non-empty `name` and `description`.
// Fails (exit 1) listing every offending file.
//
// Usage: node check-skill-frontmatter.mjs <SKILL.md>...   (paths from pre-commit)

import { readFileSync } from "node:fs";

function frontmatter(text) {
  // frontmatter is a leading `---\n ... \n---` block
  if (!text.startsWith("---")) return null;
  const end = text.indexOf("\n---", 3);
  if (end === -1) return null;
  return text.slice(3, end);
}

function hasField(fm, key) {
  // matches `key: value` or `key: >-` (block scalar) with non-empty content
  const re = new RegExp(`^${key}:\\s*(.*)$`, "m");
  const m = fm.match(re);
  if (!m) return false;
  const val = m[1].trim();
  if (val === "" || val === "|" || val === ">") return false;
  if (val === ">-" || val === "|-") {
    // block scalar: require at least one non-empty indented line after it
    const after = fm.slice(fm.indexOf(m[0]) + m[0].length);
    return /\n\s+\S/.test(after);
  }
  return true;
}

const files = process.argv.slice(2);
const failures = [];

for (const f of files) {
  let text;
  try {
    text = readFileSync(f, "utf8");
  } catch (e) {
    failures.push(`${f}: cannot read (${e.code})`);
    continue;
  }
  const fm = frontmatter(text);
  if (fm === null) {
    failures.push(`${f}: missing YAML frontmatter block`);
    continue;
  }
  if (!hasField(fm, "name")) failures.push(`${f}: frontmatter missing non-empty 'name'`);
  if (!hasField(fm, "description"))
    failures.push(`${f}: frontmatter missing non-empty 'description'`);
}

if (failures.length > 0) {
  process.stderr.write("SKILL.md frontmatter check failed:\n");
  for (const msg of failures) process.stderr.write(`  - ${msg}\n`);
  process.stderr.write("\nskills.sh requires 'name' and 'description' to discover a skill.\n");
  process.exit(1);
}

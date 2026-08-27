#!/usr/bin/env node
// manifest.mjs — deterministic core for the fkb (federated knowledge bundle) skill layer.
//
// Responsibilities (the manifest-aware concerns; all bundle MUTATION is delegated to kb*):
//   1. Load & validate workspace.okf.yaml (the sole coupling point between bundles).
//   2. Resolve name -> { path, referenceable_by, writable, publish } with fail-closed defaults.
//   3. Enforce the leak rule:  A may reference B  iff  A === B  OR  A ∈ B.referenceable_by.
//   4. Preflight the kb* dependency: the fkb skills delegate to kb skills in prose, so if kb is
//      not installed there is nothing to throw — we make the failure LOUD here instead.
//
// Zero runtime dependencies on purpose: a skills.sh-installed skill runs from a flat skills dir
// with no `npm install` step, so we parse the (small, constrained) manifest ourselves.
//
// Usage:
//   node manifest.mjs list                         # resolved bundles, one per line
//   node manifest.mjs resolve <name>               # JSON for one bundle (exit 3 if unknown)
//   node manifest.mjs can-reference <from> <to>    # exit 0 = allowed, exit 1 = denied
//   node manifest.mjs check-kb <kb-skill>...       # exit 0 = all present, exit 4 = missing
//   node manifest.mjs validate                     # exit 0 = manifest well-formed, exit 2 = not
//
// Global flags:
//   --manifest <path>   override manifest location (default: search upward for workspace.okf.yaml)
//   --json              machine-readable output where applicable

import { existsSync, readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";

// ---------------------------------------------------------------------------
// exit codes (stable contract, tested)
// ---------------------------------------------------------------------------
export const EXIT = {
  OK: 0,
  DENIED: 1, // can-reference: not allowed
  BAD_MANIFEST: 2, // manifest missing / malformed / fails validation
  UNKNOWN_BUNDLE: 3, // resolve/can-reference: name not in manifest
  MISSING_KB: 4, // check-kb: a required kb skill is not installed
  USAGE: 64, // bad CLI usage
};

// The kb skills this fkb layer delegates to. kb-promote is intentionally absent
// upstream — it is net-new in THIS repo (fkb-promote), so it is never preflighted.
export const KB_SKILLS = ["kb", "kb-init", "kb-ingest", "kb-query", "kb-lint"];

// Fail-closed defaults: an unconfigured axis is sealed and read-only.
const DEFAULTS = Object.freeze({
  referenceable_by: [], // no one may point at me
  writable: false, // no one may author into me here
  publish: null, // not published; keep links local
});

// ---------------------------------------------------------------------------
// minimal YAML: supports exactly the manifest shape (a `bundles:` map of
// flow-style entries `{ key: val, ... }`, plus simple block `key: val` entries).
// Deliberately small — we control the manifest schema, and pulling js-yaml would
// break the zero-dependency, no-install guarantee.
// ---------------------------------------------------------------------------

function stripComment(line) {
  // remove a trailing `# comment`, but not a `#` inside quotes
  let inS = false,
    inD = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === "'" && !inD) inS = !inS;
    else if (c === '"' && !inS) inD = !inD;
    else if (c === "#" && !inS && !inD) return line.slice(0, i);
  }
  return line;
}

function parseScalar(raw) {
  const t = raw.trim();
  if (t === "" || t === "~" || t === "null") return null;
  if (t === "true") return true;
  if (t === "false") return false;
  if (t === "[]") return [];
  if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) {
    return t.slice(1, -1);
  }
  if (t.startsWith("[") && t.endsWith("]")) {
    const inner = t.slice(1, -1).trim();
    if (inner === "") return [];
    return inner.split(",").map((s) => parseScalar(s));
  }
  return t;
}

function parseFlowMap(body) {
  // body is the inside of `{ ... }`. Split on top-level commas only.
  const out = {};
  let depth = 0,
    inS = false,
    inD = false,
    start = 0;
  const parts = [];
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (c === "'" && !inD) inS = !inS;
    else if (c === '"' && !inS) inD = !inD;
    else if (!inS && !inD) {
      if (c === "[" || c === "{") depth++;
      else if (c === "]" || c === "}") depth--;
      else if (c === "," && depth === 0) {
        parts.push(body.slice(start, i));
        start = i + 1;
      }
    }
  }
  parts.push(body.slice(start));
  for (const p of parts) {
    if (p.trim() === "") continue;
    const idx = p.indexOf(":");
    if (idx === -1) throw new ManifestError(`malformed manifest entry: '${p.trim()}'`);
    const key = p.slice(0, idx).trim();
    out[key] = parseScalar(p.slice(idx + 1));
  }
  return out;
}

class ManifestError extends Error {}

function parseManifest(text) {
  const lines = text.split(/\r?\n/);
  const bundles = {};
  let inBundles = false;
  let bundlesIndent = -1;

  for (let n = 0; n < lines.length; n++) {
    const rawLine = stripComment(lines[n]);
    if (rawLine.trim() === "") continue;
    const indent = rawLine.length - rawLine.trimStart().length;
    const line = rawLine.trim();

    if (!inBundles) {
      if (line === "bundles:") {
        inBundles = true;
        bundlesIndent = indent;
      }
      continue;
    }

    // inside bundles:
    if (indent <= bundlesIndent) {
      // dedented out of the bundles block
      inBundles = false;
      continue;
    }
    const idx = line.indexOf(":");
    if (idx === -1) throw new ManifestError(`line ${n + 1}: expected 'name: {...}'`);
    const name = line.slice(0, idx).trim();
    const rest = line.slice(idx + 1).trim();
    if (!rest.startsWith("{") || !rest.endsWith("}")) {
      throw new ManifestError(
        `line ${n + 1}: bundle '${name}' must use flow-style '{ path: ..., ... }'`,
      );
    }
    bundles[name] = parseFlowMap(rest.slice(1, -1));
  }

  if (Object.keys(bundles).length === 0) {
    throw new ManifestError("manifest has no 'bundles:' entries");
  }
  return bundles;
}

// ---------------------------------------------------------------------------
// load + validate + resolve
// ---------------------------------------------------------------------------

export function findManifest(startDir = process.cwd()) {
  let dir = resolve(startDir);
  for (;;) {
    const p = join(dir, "workspace.okf.yaml");
    if (existsSync(p)) return p;
    const parent = dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function normalizeBundle(name, raw) {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new ManifestError(`bundle '${name}' must be a map`);
  }
  if (typeof raw.path !== "string" || raw.path.trim() === "") {
    throw new ManifestError(`bundle '${name}': 'path' is required and must be a string`);
  }

  const ref = raw.referenceable_by ?? DEFAULTS.referenceable_by;
  if (ref === "*") {
    // keep as the wildcard sentinel
  } else if (Array.isArray(ref)) {
    if (!ref.every((x) => typeof x === "string")) {
      throw new ManifestError(`bundle '${name}': 'referenceable_by' list must be strings`);
    }
  } else {
    throw new ManifestError(`bundle '${name}': 'referenceable_by' must be '*' or a list`);
  }

  const writable = raw.writable ?? DEFAULTS.writable;
  if (typeof writable !== "boolean") {
    throw new ManifestError(`bundle '${name}': 'writable' must be true/false`);
  }

  const publish = raw.publish ?? DEFAULTS.publish;
  if (publish !== null && typeof publish !== "string") {
    throw new ManifestError(`bundle '${name}': 'publish' must be a URL string or null`);
  }

  return { name, path: raw.path, referenceable_by: ref, writable, publish };
}

export function loadWorkspace({ manifestPath, cwd = process.cwd() } = {}) {
  const p = manifestPath ? resolve(manifestPath) : findManifest(cwd);
  if (!p || !existsSync(p)) {
    throw new ManifestError(
      "no workspace.okf.yaml found (searched upward from cwd). " +
        "Copy workspace.okf.yaml.example to workspace.okf.yaml.",
    );
  }
  const bundles = parseManifest(readFileSync(p, "utf8"));
  const resolved = {};
  for (const [name, raw] of Object.entries(bundles)) {
    resolved[name] = normalizeBundle(name, raw);
  }
  return { manifestPath: p, root: dirname(p), bundles: resolved };
}

// The leak rule. A bundle may always reference itself; otherwise `from` must be
// listed in `to.referenceable_by` (or `to` is `*` = anyone).
export function canReference(ws, from, to) {
  const target = ws.bundles[to];
  if (!target) throw new ManifestError(`unknown bundle: '${to}'`);
  if (!ws.bundles[from]) throw new ManifestError(`unknown bundle: '${from}'`);
  if (from === to) return true;
  if (target.referenceable_by === "*") return true;
  return target.referenceable_by.includes(from);
}

// ---------------------------------------------------------------------------
// kb dependency preflight
// ---------------------------------------------------------------------------

// Where skills.sh installs skills (project + global, OpenCode + Claude Code).
export function skillSearchDirs(cwd = process.cwd()) {
  const home = homedir();
  return [
    join(cwd, ".agents", "skills"),
    join(cwd, ".claude", "skills"),
    join(home, ".config", "opencode", "skills"),
    join(home, ".claude", "skills"),
    join(home, ".agents", "skills"),
  ];
}

export function isKbInstalled(skill, cwd = process.cwd()) {
  for (const dir of skillSearchDirs(cwd)) {
    const p = join(dir, skill, "SKILL.md");
    try {
      if (existsSync(p) && statSync(p).isFile()) return true;
    } catch {
      /* ignore unreadable dirs */
    }
  }
  return false;
}

export function checkKb(skills, cwd = process.cwd()) {
  const missing = skills.filter((s) => !isKbInstalled(s, cwd));
  return { ok: missing.length === 0, missing };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const flags = { manifest: null, json: false };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--manifest") flags.manifest = argv[++i];
    else if (a === "--json") flags.json = true;
    else rest.push(a);
  }
  return { flags, rest };
}

function die(code, msg) {
  process.stderr.write(msg + "\n");
  process.exit(code);
}

function main(argv) {
  const { flags, rest } = parseArgs(argv);
  const [cmd, ...args] = rest;

  if (!cmd) die(EXIT.USAGE, "usage: manifest.mjs <list|resolve|can-reference|check-kb|validate>");

  // check-kb does not need a manifest.
  if (cmd === "check-kb") {
    const skills = args.length ? args : KB_SKILLS;
    const { ok, missing } = checkKb(skills);
    if (ok) {
      if (flags.json) process.stdout.write(JSON.stringify({ ok, missing }) + "\n");
      process.exit(EXIT.OK);
    }
    die(
      EXIT.MISSING_KB,
      `missing kb skill(s): ${missing.join(", ")}\n` +
        `install them with:  npx skills add stjbrown/agent-knowledge\n` +
        `(fkb delegates all bundle mutation to kb; it will not hand-roll the operation)`,
    );
  }

  let ws;
  try {
    ws = loadWorkspace({ manifestPath: flags.manifest });
  } catch (e) {
    if (e instanceof ManifestError) die(EXIT.BAD_MANIFEST, `manifest error: ${e.message}`);
    throw e;
  }

  switch (cmd) {
    case "validate":
      process.stdout.write(
        `ok: ${Object.keys(ws.bundles).length} bundle(s) in ${ws.manifestPath}\n`,
      );
      process.exit(EXIT.OK);
      break;

    case "list":
      if (flags.json) {
        process.stdout.write(JSON.stringify(ws.bundles, null, 2) + "\n");
      } else {
        for (const b of Object.values(ws.bundles)) {
          const ref = b.referenceable_by === "*" ? "*" : `[${b.referenceable_by.join(",")}]`;
          process.stdout.write(
            `${b.name}\tpath=${b.path}\twritable=${b.writable}\treferenceable_by=${ref}\tpublish=${b.publish ?? "null"}\n`,
          );
        }
      }
      process.exit(EXIT.OK);
      break;

    case "resolve": {
      const [name] = args;
      if (!name) die(EXIT.USAGE, "usage: manifest.mjs resolve <name>");
      const b = ws.bundles[name];
      if (!b) die(EXIT.UNKNOWN_BUNDLE, `unknown bundle: '${name}'`);
      process.stdout.write(JSON.stringify(b, null, flags.json ? 0 : 2) + "\n");
      process.exit(EXIT.OK);
      break;
    }

    case "can-reference": {
      const [from, to] = args;
      if (!from || !to) die(EXIT.USAGE, "usage: manifest.mjs can-reference <from> <to>");
      let allowed;
      try {
        allowed = canReference(ws, from, to);
      } catch (e) {
        die(EXIT.UNKNOWN_BUNDLE, e.message);
      }
      process.stdout.write(
        `${allowed ? "ALLOW" : "DENY"} ${from} -> ${to}` +
          (allowed ? "" : `  (${to}.referenceable_by does not include ${from})`) +
          "\n",
      );
      process.exit(allowed ? EXIT.OK : EXIT.DENIED);
      break;
    }

    default:
      die(EXIT.USAGE, `unknown command: '${cmd}'`);
  }
}

// run as CLI only when invoked directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main(process.argv.slice(2));
}

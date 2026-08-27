#!/usr/bin/env node

// manifest.test.mjs — behavior lock for the fkb manifest core.
// Run: node manifest.test.mjs   (uses node:test, zero external deps)

import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  canReference,
  checkKb,
  EXIT,
  findManifest,
  isKbInstalled,
  KB_SKILLS,
  loadWorkspace,
} from "./manifest.mjs";

// --- helpers ---------------------------------------------------------------

function tmp() {
  return mkdtempSync(join(tmpdir(), "fkb-test-"));
}

function writeManifest(dir, body) {
  writeFileSync(join(dir, "workspace.okf.yaml"), body);
  return join(dir, "workspace.okf.yaml");
}

const SAMPLE = `# workspace
bundles:
  public:  { path: ./public/docs,  referenceable_by: "*",    writable: true,  publish: https://me.example/kb }
  peer:    { path: ./peer/docs,    referenceable_by: [team], writable: true,  publish: null }
  team:    { path: ./team/docs,    referenceable_by: [peer], writable: true }
  private: { path: ./private/docs, referenceable_by: [],     writable: true }
  upstream: { path: ./upstream/docs, referenceable_by: "*",  writable: false, publish: https://them.example/kb }
`;

// --- parsing & fail-closed defaults ----------------------------------------

test("loads all bundles and resolves fields", () => {
  const d = tmp();
  const p = writeManifest(d, SAMPLE);
  const ws = loadWorkspace({ manifestPath: p });
  assert.deepEqual(Object.keys(ws.bundles).sort(), [
    "peer",
    "private",
    "public",
    "team",
    "upstream",
  ]);
  assert.equal(ws.bundles.public.publish, "https://me.example/kb");
  assert.equal(ws.bundles.public.referenceable_by, "*");
  rmSync(d, { recursive: true, force: true });
});

test("fail-closed defaults: omitted writable=false, omitted publish=null", () => {
  const d = tmp();
  const p = writeManifest(d, "bundles:\n  x: { path: ./x/docs }\n");
  const ws = loadWorkspace({ manifestPath: p });
  assert.equal(ws.bundles.x.writable, false, "writable must default false");
  assert.equal(ws.bundles.x.publish, null, "publish must default null");
  assert.deepEqual(ws.bundles.x.referenceable_by, [], "referenceable_by must default []");
  rmSync(d, { recursive: true, force: true });
});

test("team has no explicit publish -> null; still parses", () => {
  const d = tmp();
  const p = writeManifest(d, SAMPLE);
  const ws = loadWorkspace({ manifestPath: p });
  assert.equal(ws.bundles.team.publish, null);
  assert.equal(ws.bundles.upstream.writable, false);
  rmSync(d, { recursive: true, force: true });
});

test("missing path is a manifest error", () => {
  const d = tmp();
  const p = writeManifest(d, "bundles:\n  broken: { writable: true }\n");
  assert.throws(() => loadWorkspace({ manifestPath: p }), /path.*required/);
  rmSync(d, { recursive: true, force: true });
});

test("empty bundles is a manifest error", () => {
  const d = tmp();
  const p = writeManifest(d, "bundles:\n");
  assert.throws(() => loadWorkspace({ manifestPath: p }), /no 'bundles:' entries/);
  rmSync(d, { recursive: true, force: true });
});

// --- the leak rule ---------------------------------------------------------

test("a bundle may always reference itself, even if sealed", () => {
  const d = tmp();
  const p = writeManifest(d, SAMPLE);
  const ws = loadWorkspace({ manifestPath: p });
  assert.equal(canReference(ws, "private", "private"), true);
  rmSync(d, { recursive: true, force: true });
});

test("'*' means anyone may reference", () => {
  const d = tmp();
  const p = writeManifest(d, SAMPLE);
  const ws = loadWorkspace({ manifestPath: p });
  assert.equal(canReference(ws, "private", "public"), true);
  assert.equal(canReference(ws, "peer", "public"), true);
  rmSync(d, { recursive: true, force: true });
});

test("'[]' means no one may reference (private is sealed)", () => {
  const d = tmp();
  const p = writeManifest(d, SAMPLE);
  const ws = loadWorkspace({ manifestPath: p });
  assert.equal(canReference(ws, "public", "private"), false);
  assert.equal(canReference(ws, "peer", "private"), false);
  rmSync(d, { recursive: true, force: true });
});

test("mutual, unranked peers: peer <-> team both allowed", () => {
  const d = tmp();
  const p = writeManifest(d, SAMPLE);
  const ws = loadWorkspace({ manifestPath: p });
  assert.equal(canReference(ws, "peer", "team"), true, "peer -> team");
  assert.equal(canReference(ws, "team", "peer"), true, "team -> peer");
  rmSync(d, { recursive: true, force: true });
});

test("non-peer denied: team may not reference private, public may not reference peer", () => {
  const d = tmp();
  const p = writeManifest(d, SAMPLE);
  const ws = loadWorkspace({ manifestPath: p });
  assert.equal(canReference(ws, "public", "peer"), false);
  assert.equal(canReference(ws, "team", "private"), false);
  rmSync(d, { recursive: true, force: true });
});

test("referencing an unknown bundle throws", () => {
  const d = tmp();
  const p = writeManifest(d, SAMPLE);
  const ws = loadWorkspace({ manifestPath: p });
  assert.throws(() => canReference(ws, "public", "ghost"), /unknown bundle/);
  assert.throws(() => canReference(ws, "ghost", "public"), /unknown bundle/);
  rmSync(d, { recursive: true, force: true });
});

// --- kb preflight ----------------------------------------------------------

test("check-kb reports missing when skills absent (isolated cwd)", () => {
  const d = tmp(); // empty dir: no .agents/.claude skills here
  const res = checkKb(["kb-ingest"], d);
  // Note: global dirs may exist on the host; assert the shape, and that an
  // obviously-fake skill is reported missing.
  const fake = checkKb(["kb-does-not-exist-xyz"], d);
  assert.equal(fake.ok, false);
  assert.deepEqual(fake.missing, ["kb-does-not-exist-xyz"]);
  rmSync(d, { recursive: true, force: true });
  void res;
});

test("check-kb reports present when a project skill exists", () => {
  const d = tmp();
  const skillDir = join(d, ".agents", "skills", "kb-ingest");
  mkdirSync(skillDir, { recursive: true });
  writeFileSync(join(skillDir, "SKILL.md"), "---\nname: kb-ingest\n---\n");
  assert.equal(isKbInstalled("kb-ingest", d), true);
  const res = checkKb(["kb-ingest"], d);
  assert.equal(res.ok, true);
  assert.deepEqual(res.missing, []);
  rmSync(d, { recursive: true, force: true });
});

test("KB_SKILLS does not include kb-promote (net-new here, not upstream)", () => {
  assert.ok(!KB_SKILLS.includes("kb-promote"));
  assert.ok(KB_SKILLS.includes("kb-ingest"));
});

// --- discovery -------------------------------------------------------------

test("findManifest walks upward from a nested cwd", () => {
  const d = tmp();
  writeManifest(d, SAMPLE);
  const nested = join(d, "a", "b", "c");
  mkdirSync(nested, { recursive: true });
  assert.equal(findManifest(nested), join(d, "workspace.okf.yaml"));
  rmSync(d, { recursive: true, force: true });
});

test("EXIT codes are stable", () => {
  assert.deepEqual(EXIT, {
    OK: 0,
    DENIED: 1,
    BAD_MANIFEST: 2,
    UNKNOWN_BUNDLE: 3,
    MISSING_KB: 4,
    USAGE: 64,
  });
});

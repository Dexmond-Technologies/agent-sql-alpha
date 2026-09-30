import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const packageJson = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const packageLock = JSON.parse(readFileSync(join(root, "package-lock.json"), "utf8"));
const cargoToml = readFileSync(join(root, "src-tauri", "Cargo.toml"), "utf8");
const cargoLock = readFileSync(join(root, "src-tauri", "Cargo.lock"), "utf8");

const escapeCell = value => String(value ?? "Not declared").replaceAll("|", "\\|").replaceAll("\n", " ");
const packageNameFromPath = path => {
  const leaf = path.slice(path.lastIndexOf("node_modules/") + "node_modules/".length);
  const parts = leaf.split("/");
  return parts[0].startsWith("@") ? `${parts[0]}/${parts[1]}` : parts[0];
};
const npmDirect = new Map([
  ...Object.entries(packageJson.dependencies || {}).map(([name, range]) => [name, { scope: "Runtime direct", range }]),
  ...Object.entries(packageJson.devDependencies || {}).map(([name, range]) => [name, { scope: "Build/test direct", range }]),
]);
const npmPackages = Object.entries(packageLock.packages || {}).filter(([path]) => path.includes("node_modules/")).map(([path, value]) => {
  const name = value.name || packageNameFromPath(path); const direct = npmDirect.get(name);
  return { name, version: value.version, license: value.license || "Not declared in lock metadata", status: direct ? `${direct.scope}; requested ${direct.range}; locked` : "Transitive; locked", repository: typeof value.repository === "string" ? value.repository : value.repository?.url || "—" };
}).sort((a, b) => a.name.localeCompare(b.name) || String(a.version).localeCompare(String(b.version)));

const sectionNames = section => {
  const match = cargoToml.match(new RegExp(`\\[${section.replaceAll("-", "\\-")}\\]([\\s\\S]*?)(?=\\n\\[|$)`));
  if (!match) return new Set();
  return new Set(Array.from(match[1].matchAll(/^([A-Za-z0-9_-]+)\s*=/gm), item => item[1]));
};
const rustRuntime = sectionNames("dependencies");
const rustBuild = sectionNames("build-dependencies");
const cargoSourceRoot = join(process.env.CARGO_HOME || join(process.env.USERPROFILE || process.env.HOME || "", ".cargo"), "registry", "src");
const cargoIndexes = existsSync(cargoSourceRoot) ? readdirSync(cargoSourceRoot).map(name => join(cargoSourceRoot, name)) : [];
const cargoManifest = (name, version) => {
  for (const index of cargoIndexes) { const path = join(index, `${name}-${version}`, "Cargo.toml"); if (existsSync(path)) return readFileSync(path, "utf8"); }
  return "";
};
const cargoPackages = cargoLock.split("[[package]]").slice(1).map(block => ({ name: block.match(/^name = "([^"]+)"/m)?.[1], version: block.match(/^version = "([^"]+)"/m)?.[1], source: block.match(/^source = "([^"]+)"/m)?.[1] })).filter(item => item.name && item.version && item.name !== packageJson.name);
const rustPackages = cargoPackages.map(item => {
  const status = rustRuntime.has(item.name) ? "Runtime direct; locked" : rustBuild.has(item.name) ? "Build direct; locked" : "Transitive; locked";
  const manifest=cargoManifest(item.name,item.version);const license=manifest.match(/^license = "([^"]+)"/m)?.[1] || "Not available in local package metadata";const repository=manifest.match(/^repository = "([^"]+)"/m)?.[1] || "—";
  return { name: item.name, version: item.version, license, status, repository };
}).sort((a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version));

const table = rows => ["| Component | Locked version | License expression | Version status | Upstream |", "|---|---:|---|---|---|", ...rows.map(row => `| ${escapeCell(row.name)} | ${escapeCell(row.version)} | ${escapeCell(row.license)} | ${escapeCell(row.status)} | ${escapeCell(row.repository)} |`)].join("\n");
const generated = `# Third-Party Software and Asset Inventory

Generated from \`package-lock.json\`, \`Cargo.lock\`, locally available package metadata, and the repository asset inventory on 2026-09-27.

This inventory records the exact versions locked for agentSQL 0.0.1-alpha and the license identifiers declared by each package. “Locked” means reproducible in the current lockfile; it does not claim that the version is the newest release or free of vulnerabilities. Dependency upgrades require security, compatibility, and license review. License identifiers are informational and are not legal advice.

## Distribution obligations and manually reviewed assets

| Component | Version/source | License | Version status and use |
|---|---|---|---|
| SQLite amalgamation (through rusqlite/libsqlite3-sys bundled feature) | Version selected by the locked Rust dependency | Public Domain | Embedded runtime database engine; transitive source bundle |
| Orbitron font | Repository TTF assets; Google Fonts family | SIL Open Font License 1.1 | Bundled UI asset; exact upstream release tag is not recorded in this repository |
| Space Grotesk font | Repository TTF assets; Google Fonts family | SIL Open Font License 1.1 | Bundled UI asset; exact upstream release tag is not recorded in this repository |
| Microsoft WebView2 | Supplied by Windows, accessed through Tauri/Wry | Microsoft software terms | System runtime; not redistributed as source by this repository |
| WebKitGTK | Supplied by the Linux distribution, accessed through Tauri/Wry | LGPL-2.1-or-later and component licenses | System runtime; package version depends on the target distribution |
| WebKit | Supplied by macOS, accessed through Tauri/Wry | Apple/system and upstream component terms | System runtime; version depends on macOS |

Dexmond Technologies logos, product naming, and original application code are first-party material and are therefore outside this third-party list. No copied application source snippets are intentionally vendored outside the package manager dependencies and the assets identified above.

## JavaScript and frontend packages

${table(npmPackages)}

## Rust and native packages

${table(rustPackages)}

## Maintenance

- Regenerate this file after any lockfile or bundled-asset change with \`node scripts/generate-third-party-notices.mjs\`.
- Review packages marked “Not declared” against their upstream distribution before release.
- Retain required copyright and license texts in production installers. This inventory is not a substitute for those notices.
- Run dependency vulnerability and license-policy scans before every banking-sector release; a locked version is not automatically an approved version.
`;

writeFileSync(join(root, "THIRD_PARTY_NOTICES.md"), generated, "utf8");
console.log(`Wrote THIRD_PARTY_NOTICES.md with ${npmPackages.length} JavaScript packages and ${rustPackages.length} Rust packages.`);

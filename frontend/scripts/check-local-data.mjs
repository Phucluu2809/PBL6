/** Read-only manual verification of the repository's dataset, not a fixture test. */
import assert from 'node:assert/strict';
import { createDatasetReader } from '../server/dataset.mjs';
const reader = createDatasetReader();
const catalog = await reader.getCatalog(true);
assert.equal(catalog.readOnly, true);
assert.equal(catalog.warnings.length, 0, JSON.stringify(catalog.warnings));
const byPerson = Object.fromEntries(
  ['P001', 'P002', 'P003', 'UNASSIGNED'].map((id) => [
    id,
    catalog.samples.filter((s) => s.person === id).length,
  ]),
);
const schemas = [...new Set(catalog.samples.map((s) => s.schema))];
const checked = [];
for (const schema of schemas) {
  const sample = catalog.samples.find((s) => s.schema === schema && s.rowCount > 0);
  if (!sample) continue;
  const detail = await reader.getSample(sample.id);
  assert.equal(detail.readOnly, true);
  assert.equal(detail.rowCount, sample.rowCount);
  assert.match(detail.sha256, /^[a-f0-9]{64}$/);
  assert.ok(detail.channels.length);
  checked.push({
    schema,
    label: sample.name,
    rows: detail.rowCount,
    channels: detail.channels.map((c) => c.key),
  });
}
console.log(
  JSON.stringify(
    {
      samples: catalog.samples.length,
      skippedSessions: catalog.skippedSessions,
      byPerson,
      warnings: catalog.warnings,
      checked,
    },
    null,
    2,
  ),
);

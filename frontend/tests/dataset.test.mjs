import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { join, resolve, dirname, basename } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';
import {
  createDatasetReader,
  datasetPlugin,
  parseCSVLine,
  identifyLabel,
} from '../server/dataset.mjs';

test('CSV đọc số thập phân, nhãn có dấu phẩy và dấu nháy', () => {
  assert.deepEqual(parseCSVLine('1,"a,b","c""d",'), ['1', 'a,b', 'c"d', '']);
});
test('Chỉ ghép ba hồ sơ từ alias rõ ràng, giữ riêng đối chứng và tên khác', () => {
  assert.equal(identifyLabel('Tai_phongTai'), 'P001');
  assert.equal(identifyLabel('Duong_coffe'), 'P002');
  assert.equal(identifyLabel('phucluu_1'), 'P003');
  assert.equal(identifyLabel('khongkhi_phongTai'), null);
  assert.equal(identifyLabel('Tuan_phongTai'), null);
  assert.equal(identifyLabel('aDung'), null);
});
test('Đọc fixture legacy/S3, giữ khoảng trống lỗi, không suy COMPLETE là QC PASS và không sửa nguồn', async () => {
  const root = await mkdtemp(join(tmpdir(), 'robonose-readonly-'));
  try {
    const s3 = join(root, '2026-11-16', 'Tai_1');
    await mkdir(s3, { recursive: true });
    const raw =
      'mono_s,timestamp,phase,tgs2602_voltage_v,tgs2602_status,tgs2602_valid,gas_resistance_ohm,gas_valid,heater_stable,new_data\n100,2026-11-16T10:00:00+07:00,BASELINE,0.5,OK,true,1000,true,true,true\n101,2026-11-16T10:00:01+07:00,EXPOSURE,0.7,OK,false,1100,false,true,true\n102,2026-11-16T10:00:02+07:00,RECOVERY,,ERROR,false,1200,true,true,true\n';
    await writeFile(join(s3, 'raw.csv'), raw);
    await writeFile(
      join(s3, 'metadata.json'),
      JSON.stringify({
        name: 'Tai',
        status: 'COMPLETE',
        schema: 'robonose.dataset.v1',
        source_raw: '../../outside.csv',
        config: { baseline_s: 60, exposure_s: 120, recovery_s: 60 },
      }),
    );
    await writeFile(join(s3, 'summary.json'), JSON.stringify({ quality: 'UNCONFIGURED' }));
    const legacy = join(root, '2026-10-25', 'Duong_20261025_120000_abc');
    await mkdir(legacy, { recursive: true });
    await writeFile(
      join(legacy, 'raw.csv'),
      'elapsed_s,timestamp,phase,mq135_voltage_v,mq135_status,mq135_fresh\n0,2026-10-25T12:00:00+07:00,BASELINE,0.2,OK,True\n1,2026-10-25T12:00:01+07:00,EXPOSURE,0.4,OK,True\n',
    );
    const session = join(root, 'session');
    await mkdir(session);
    await writeFile(join(session, 'raw.csv'), raw);
    const before = createHash('sha256')
      .update(await readFile(join(s3, 'raw.csv')))
      .digest('hex');
    const reader = createDatasetReader(root);
    const catalog = await reader.getCatalog();
    assert.equal(catalog.samples.length, 2);
    assert.equal(catalog.skippedSessions, 1);
    assert.equal(catalog.readOnly, true);
    const sample = catalog.samples.find((s) => s.person === 'P001');
    assert.equal(sample.qc, 'REVIEW');
    assert.equal(sample.qcSource, 'UNCONFIGURED');
    const detail = await reader.getSample(sample.id);
    assert.equal(detail.sha256, before);
    assert.equal(detail.points[0].t, 0);
    assert.equal(detail.points[1].values.tgs2602_voltage_v, null);
    assert.equal(detail.points[1].values.gas_resistance_ohm, null);
    assert.equal(detail.points[2].values.tgs2602_voltage_v, null);
    assert.equal(detail.points[2].values.gas_resistance_ohm, 1200);
    assert.equal(detail.channels.find((c) => c.key === 'tgs2602_voltage_v').invalid, 2);
    assert.equal(detail.segments.length, 3);
    assert.equal(await reader.getSample('../../outside.csv'), null);
    assert.equal(
      createHash('sha256')
        .update(await readFile(join(s3, 'raw.csv')))
        .digest('hex'),
      before,
    );
  } finally {
    assert.equal(dirname(resolve(root)), resolve(tmpdir()));
    assert.ok(basename(root).startsWith('robonose-readonly-'));
    await rm(root, { recursive: true, force: true });
  }
});
test('Dataset middleware từ chối POST/PUT/PATCH/DELETE, không có endpoint ghi dữ liệu', async () => {
  let handler;
  datasetPlugin().configureServer({
    middlewares: {
      use(fn) {
        handler = fn;
      },
    },
  });
  for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
    let body = '';
    const headers = {};
    const response = {
      setHeader(k, v) {
        headers[k] = v;
      },
      end(v) {
        body = v;
      },
    };
    await handler({ url: '/api/dataset/sample?id=anything', method }, response, () =>
      assert.fail('Must not continue'),
    );
    assert.equal(response.statusCode, 405);
    assert.equal(headers.Allow, 'GET, HEAD');
    assert.match(body, /Dataset/);
  }
});

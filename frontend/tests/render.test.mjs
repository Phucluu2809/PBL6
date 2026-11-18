import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToString } from 'react-dom/server';

test('Tất cả màn hình render được, route quản trị chặn Viewer, có form đăng nhập demo', async () => {
  const storage = () => {
    const map = new Map();
    return {
      getItem: (k) => map.get(k) ?? null,
      setItem: (k, v) => map.set(k, String(v)),
      removeItem: (k) => map.delete(k),
    };
  };
  globalThis.localStorage = storage();
  globalThis.sessionStorage = storage();
  globalThis.sessionStorage.setItem('robonose.demo-role', 'Super Admin');
  globalThis.location = { hash: '' };
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { createSeed: makeSeed } = await server.ssrLoadModule('/src/data.ts');
    const legacy = makeSeed();
    legacy.users[0].name = 'Old demo user';
    legacy.people[0].name = 'Old demo participant';
    globalThis.localStorage.setItem(
      'robonose.frontend.v1',
      JSON.stringify({ version: 1, data: legacy }),
    );
    const { default: App } = await server.ssrLoadModule('/src/App.tsx');
    for (const path of [
      'test',
      'dashboard',
      'users',
      'devices',
      'experiments',
      'samples',
      'people',
      'ai',
      'models',
      'roles',
      'security',
      'settings',
      'health',
      'reports',
      'profile',
    ]) {
      globalThis.location.hash = '#/' + path;
      const html = renderToString(React.createElement(App));
      assert.ok(html.includes('RoboNose'), path);
      assert.ok(!html.includes('403 ·'), path);
      assert.ok(!html.includes('Không tìm thấy màn hình'), path);
    }
    globalThis.sessionStorage.setItem('robonose.demo-role', 'Viewer');
    globalThis.location.hash = '#/users';
    assert.match(renderToString(React.createElement(App)), /403 · Không có quyền truy cập/);
    globalThis.sessionStorage.setItem('robonose.demo-role', 'Tester');
    globalThis.location.hash = '#/test';
    const tester = renderToString(React.createElement(App));
    assert.match(tester, /Thu mùi\. Kiểm tra danh tính\./);
    assert.ok(!tester.includes('403 ·'));
    assert.ok(!tester.includes('Quản lý người dùng'));
    assert.ok(!tester.includes('Model Registry'));
    assert.ok(!tester.includes('Chọn trước danh tính'));
    globalThis.location.hash = '#/users';
    assert.match(renderToString(React.createElement(App)), /403 · Không có quyền truy cập/);
    globalThis.sessionStorage.setItem('robonose.demo-session', 'out');
    assert.match(renderToString(React.createElement(App)), /Vào workspace/);
    const { createSeed } = await server.ssrLoadModule('/src/data.ts');
    const { isStore } = await server.ssrLoadModule('/src/domain.ts');
    const seed = createSeed();
    assert.equal(isStore(seed), true);
    assert.deepEqual(
      seed.users.map((u) => u.name),
      ['Nguyễn Văn Tài', 'Nguyễn Văn Dương', 'Lưu Hoàng Phúc'],
    );
    assert.equal(seed.samples.length, 0);
    const { mockService, migrateStorePayload } =
      await server.ssrLoadModule('/src/services/store.ts');
    assert.equal(mockService.getSnapshot().users[0].name, 'Nguyễn Văn Tài');
    assert.equal(mockService.getSnapshot().people[0].name, 'Nguyễn Văn Tài');
    assert.ok(mockService.getSnapshot().users[2].roles.includes('Tester'));
    const oldV2 = makeSeed();
    oldV2.users[0].title = 'Preserve this title';
    oldV2.people[0].note = 'Preserve consent record';
    oldV2.permissions.Operator.devices = [];
    delete oldV2.permissions.Tester;
    for (const row of Object.values(oldV2.permissions)) delete row.testing;
    oldV2.users[2].roles = oldV2.users[2].roles.filter((r) => r !== 'Tester');
    const migrated = migrateStorePayload({ version: 2, data: oldV2 });
    assert.equal(migrated.users[0].title, 'Preserve this title');
    assert.equal(migrated.people[0].note, 'Preserve consent record');
    assert.deepEqual(migrated.permissions.Operator.devices, []);
    assert.ok(migrated.users[2].roles.includes('Tester'));
    assert.ok(migrated.permissions.Tester.testing.includes('create'));
    mockService.update((s) => ({
      ...s,
      samples: [{ id: 'DATA-injected', person: 'P001', readOnly: true }],
    }));
    assert.equal(mockService.getSnapshot().samples.length, 0);
    const { RawSignalChart } = await server.ssrLoadModule('/src/components/DatasetCharts.tsx');
    const chart = renderToString(
      React.createElement(RawSignalChart, {
        channel: 'gas_resistance_ohm',
        data: {
          points: [
            { t: 0, phase: 'BASELINE', values: { gas_resistance_ohm: 1000 } },
            { t: 1, phase: 'EXPOSURE', values: { gas_resistance_ohm: null } },
            { t: 2, phase: 'RECOVERY', values: { gas_resistance_ohm: 1200 } },
          ],
          segments: [],
          channels: [{ key: 'gas_resistance_ohm', label: 'BME gas', unit: 'Ω' }],
        },
      }),
    );
    assert.ok(chart.includes('tín hiệu thật từ raw.csv'));
    assert.ok(!chart.includes('NaN'));
    seed.users[0].roles = ['Unknown'];
    assert.equal(isStore(seed), false);
  } finally {
    await server.close();
    delete globalThis.localStorage;
    delete globalThis.sessionStorage;
    delete globalThis.location;
  }
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  can,
  defaultPermissions,
  validateUser,
  csvCell,
  nextPhase,
  isStore,
  upgradePermissions,
  roleHome,
} from '../src/domain.ts';
import type { User } from '../src/types.ts';
test('Viewer không điều khiển thiết bị, quản trị user hoặc xuất dữ liệu', () => {
  const m = defaultPermissions();
  assert.equal(can(m, 'Viewer', 'samples'), true);
  assert.equal(can(m, 'Viewer', 'users'), false);
  assert.equal(can(m, 'Viewer', 'experiments', 'control'), false);
  assert.equal(can(m, 'Viewer', 'samples', 'export'), false);
});
test('Operator vận hành; Researcher phân tích; quyền cập nhật phản ánh ngay', () => {
  const m = defaultPermissions();
  assert.equal(can(m, 'Operator', 'devices', 'control'), true);
  assert.equal(can(m, 'Researcher', 'devices', 'control'), false);
  assert.equal(can(m, 'Researcher', 'samples', 'export'), true);
  m.Operator.devices = [];
  assert.equal(can(m, 'Operator', 'devices', 'control'), false);
});
test('Không cho email trùng bất kể hoa thường; cho phép sửa chính tài khoản', () => {
  const users = [{ id: '1', email: 'sample@lab.test' }] as User[];
  const form = { name: 'Nguyễn An', email: 'SAMPLE@lab.test', roles: ['Viewer'] as User['roles'] };
  assert.match(validateUser(form, users), /đã được sử dụng/);
  assert.equal(validateUser(form, users, '1'), '');
  assert.match(validateUser({ ...form, roles: [] }, []), /ít nhất/);
  assert.match(validateUser({ ...form, name: ' ' }, []), /họ tên/);
});
test('Chuỗi pha giữ đầy đủ bước chờ và đặt tên', () => {
  assert.equal(nextPhase('BASELINE'), 'WAIT_EXPOSURE');
  assert.equal(nextPhase('EXPOSURE'), 'WAIT_RECOVERY');
  assert.equal(nextPhase('RECOVERY'), 'WAIT_FINISH');
  assert.equal(nextPhase('WAIT_FINISH'), 'WAIT_NAME');
});
test('CSV bảo vệ ô công thức và escape dấu nháy / dấu phẩy', () => {
  assert.equal(csvCell('a,"b"'), '"a,""b"""');
  assert.equal(csvCell('=SUM(A1:A2)'), '"\'=SUM(A1:A2)"');
  assert.equal(csvCell('@cmd'), '"\'@cmd"');
});
test('Từ chối backup thiếu dữ liệu hoặc sai schema', () => {
  assert.equal(isStore(null), false);
  assert.equal(isStore({ users: [] }), false);
  assert.equal(isStore({ users: [{ id: 'bad' }] }), false);
});
test('Tester kiểm tra mẫu và thu thử; không quản trị hoặc sửa dataset', () => {
  const matrix = defaultPermissions();
  assert.equal(can(matrix, 'Tester', 'testing', 'create'), true);
  assert.equal(can(matrix, 'Tester', 'testing', 'control'), true);
  assert.equal(can(matrix, 'Tester', 'samples', 'view'), true);
  for (const module of [
    'users',
    'roles',
    'models',
    'security',
    'settings',
    'people',
    'experiments',
  ] as const)
    assert.equal(can(matrix, 'Tester', module), false, module);
  assert.equal(can(matrix, 'Tester', 'samples', 'edit'), false);
  assert.equal(can(matrix, 'Tester', 'samples', 'delete'), false);
  assert.equal(roleHome('Tester'), '/test');
  assert.equal(roleHome('Admin'), '/dashboard');
});
test('Nâng quyền schema cũ giữ cấu hình hiện có và thêm module/role Tester', () => {
  const old = defaultPermissions() as any;
  delete old.Tester;
  for (const row of Object.values(old) as any[]) delete row.testing;
  old.Operator.devices = [];
  old.Researcher.samples = ['view'];
  const upgraded = upgradePermissions(old);
  assert.deepEqual(upgraded.Operator.devices, []);
  assert.deepEqual(upgraded.Researcher.samples, ['view']);
  assert.equal(can(upgraded, 'Tester', 'testing', 'control'), true);
  assert.equal(can(upgraded, 'Operator', 'testing', 'control'), true);
});

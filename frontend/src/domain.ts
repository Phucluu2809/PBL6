import type { Module, Permission, PermissionMatrix, Role, Store, User } from './types.ts';
export const roles: Role[] = ['Super Admin', 'Admin', 'Operator', 'Researcher', 'Viewer', 'Tester'];
export const modules: Module[] = [
  'testing',
  'dashboard',
  'devices',
  'experiments',
  'samples',
  'people',
  'ai',
  'models',
  'users',
  'roles',
  'security',
  'settings',
  'reports',
  'profile',
];
export const actions: Permission[] = [
  'view',
  'create',
  'edit',
  'delete',
  'control',
  'export',
  'manage',
];
export function defaultPermissions(): PermissionMatrix {
  return Object.fromEntries(
    roles.map((role) => [
      role,
      Object.fromEntries(
        modules.map((module) => {
          let p: Permission[] = [];
          if (role === 'Super Admin') p = [...actions];
          else if (role === 'Admin') p = [...actions];
          else if (role === 'Tester')
            p =
              module === 'testing'
                ? ['view', 'create', 'control']
                : module === 'profile'
                  ? ['view', 'edit']
                  : ['dashboard', 'samples'].includes(module)
                    ? ['view']
                    : [];
          else if (role === 'Operator')
            p = [
              'testing',
              'dashboard',
              'devices',
              'experiments',
              'samples',
              'people',
              'profile',
            ].includes(module)
              ? [
                  'view',
                  'create',
                  'edit',
                  ...(module === 'devices' || module === 'experiments' || module === 'testing'
                    ? ['control' as Permission]
                    : []),
                ]
              : [];
          else if (role === 'Researcher')
            p = [
              'testing',
              'dashboard',
              'samples',
              'people',
              'ai',
              'models',
              'reports',
              'profile',
            ].includes(module)
              ? ['view', 'create', 'edit', 'export']
              : module === 'experiments' || module === 'devices'
                ? ['view']
                : [];
          else
            p = ['dashboard', 'samples', 'experiments', 'reports', 'profile'].includes(module)
              ? ['view']
              : [];
          return [module, p];
        }),
      ),
    ]),
  ) as PermissionMatrix;
}
export function can(
  matrix: PermissionMatrix,
  role: Role,
  module: Module,
  action: Permission = 'view',
) {
  return matrix[role]?.[module]?.includes(action) ?? false;
}
/** Add newly introduced modules and roles without resetting existing permissions. */
export function upgradePermissions(existing: unknown): PermissionMatrix {
  const defaults = defaultPermissions();
  if (!existing || typeof existing !== 'object') return defaults;
  const old = existing as Partial<PermissionMatrix>;
  return Object.fromEntries(
    roles.map((role) => [
      role,
      Object.fromEntries(
        modules.map((module) => [module, old[role]?.[module] ?? defaults[role][module]]),
      ),
    ]),
  ) as PermissionMatrix;
}
export function roleHome(role: Role) {
  return role === 'Tester' ? '/test' : '/dashboard';
}
export function validateUser(
  user: Pick<User, 'name' | 'email' | 'roles'>,
  users: User[],
  id?: string,
): string {
  if (!user.name.trim()) return 'Vui lòng nhập họ tên.';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(user.email.trim())) return 'Email chưa đúng định dạng.';
  if (users.some((u) => u.id !== id && u.email.toLowerCase() === user.email.trim().toLowerCase()))
    return 'Email đã được sử dụng.';
  if (!user.roles.length) return 'Chọn ít nhất một vai trò.';
  return '';
}
export const phases = [
  'MONITOR',
  'BASELINE',
  'WAIT_EXPOSURE',
  'EXPOSURE',
  'WAIT_RECOVERY',
  'RECOVERY',
  'WAIT_FINISH',
  'WAIT_NAME',
] as const;
export function nextPhase(phase: string): string {
  const index = phases.indexOf(phase as (typeof phases)[number]);
  return phases[(index + 1) % phases.length];
}
export function csvCell(value: unknown) {
  const text = String(value ?? '');
  return '"' + (/^[=+@\-\t\r]/.test(text) ? "'" : '') + text.replaceAll('"', '""') + '"';
}
export function isStore(value: unknown): value is Store {
  if (!value || typeof value !== 'object') return false;
  const s = value as Record<string, unknown>;
  const list = (key: string, check: (v: Record<string, any>) => boolean) =>
    Array.isArray(s[key]) &&
    (s[key] as unknown[]).every(
      (v) => v !== null && typeof v === 'object' && check(v as Record<string, any>),
    );
  const strings = (v: Record<string, unknown>, keys: string[]) =>
    keys.every((k) => typeof v[k] === 'string');
  if (
    !list(
      'users',
      (u) =>
        strings(u, ['id', 'name', 'email', 'department', 'title', 'phone', 'lastLogin', 'group']) &&
        Array.isArray(u.roles) &&
        u.roles.length > 0 &&
        u.roles.every((r: unknown) => roles.includes(r as Role)) &&
        ['Active', 'Locked', 'Disabled', 'Pending'].includes(u.status) &&
        typeof u.mfa === 'boolean',
    ) ||
    !(s.users as unknown[]).length
  )
    return false;
  if (
    !list(
      'samples',
      (v) =>
        strings(v, ['id', 'person', 'date', 'device', 'protocol', 'note']) &&
        ['PASS', 'REVIEW', 'FAIL'].includes(v.qc) &&
        typeof v.duration === 'number' &&
        Number.isFinite(v.duration),
    )
  )
    return false;
  if (!list('people', (v) => strings(v, ['id', 'name', 'note']) && typeof v.consent === 'boolean'))
    return false;
  if (
    !list(
      'models',
      (v) =>
        strings(v, ['id', 'name', 'version', 'channels', 'metrics', 'date']) &&
        typeof v.active === 'boolean',
    )
  )
    return false;
  if (!list('audits', (v) => strings(v, ['id', 'actor', 'action', 'target', 'time']))) return false;
  if (
    !list(
      'invitations',
      (v) =>
        strings(v, ['id', 'email', 'date']) &&
        roles.includes(v.role) &&
        ['Pending', 'Accepted', 'Expired', 'Revoked'].includes(v.status),
    )
  )
    return false;
  if (
    !list(
      'results',
      (v) =>
        strings(v, ['id', 'sample', 'model', 'result', 'time']) &&
        ['Nhận diện', 'Matching'].includes(v.kind) &&
        typeof v.score === 'number' &&
        Number.isFinite(v.score),
    )
  )
    return false;
  if (
    !s.settings ||
    typeof s.settings !== 'object' ||
    !Object.values(s.settings).every((v) => typeof v === 'string')
  )
    return false;
  const settings = s.settings as Record<string, string>;
  if (
    ![
      'labName',
      'email',
      'timezone',
      'language',
      'baseline',
      'exposure',
      'recovery',
      'passwordLength',
      'sessionTimeout',
      'auditRetention',
      'sampleRetention',
      'requireMfa',
      'notifications',
    ].every((k) => typeof settings[k] === 'string')
  )
    return false;
  if (
    !['baseline', 'exposure', 'recovery'].every(
      (k) =>
        Number.isFinite(Number(settings[k])) &&
        Number(settings[k]) > 0 &&
        Number(settings[k]) <= 86400,
    )
  )
    return false;
  const matrix = s.permissions as PermissionMatrix;
  if (
    !matrix ||
    !roles.every((r) =>
      modules.every(
        (m) => Array.isArray(matrix[r]?.[m]) && matrix[r][m].every((a) => actions.includes(a)),
      ),
    )
  )
    return false;
  return new Set((s.users as User[]).map((u) => u.id)).size === (s.users as User[]).length;
}

import { useSyncExternalStore } from 'react';
import { createSeed } from '../data';
import type { Store } from '../types';
import { isStore, upgradePermissions } from '../domain';
const KEY = 'robonose.frontend.v1';
let storageWarning = '';
export function migrateStorePayload(value: unknown): Store | null {
  if (!value || typeof value !== 'object') return null;
  const parsed = value as { version?: number; data?: Store };
  if (parsed.version === 3 && isStore(parsed.data)) return parsed.data;
  if ((parsed.version === 1 || parsed.version === 2) && parsed.data) {
    const upgraded = { ...parsed.data, permissions: upgradePermissions(parsed.data.permissions) };
    if (!isStore(upgraded)) return null;
    if (parsed.version === 2)
      return {
        ...upgraded,
        users: upgraded.users.map((user) =>
          user.id === 'USR-003'
            ? { ...user, roles: Array.from(new Set([...user.roles, 'Tester' as const])) }
            : user,
        ),
      };
    const seed = createSeed();
    return {
      ...upgraded,
      users: seed.users,
      people: seed.people,
      samples: [],
      results: [],
      audits: [],
      invitations: [],
    };
  }
  return null;
}
function read(): Store {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      const migrated = migrateStorePayload(parsed);
      if (migrated) return migrated;
      storageWarning = 'Dữ liệu demo không tương thích; đang dùng bộ dữ liệu mẫu.';
    }
  } catch {
    storageWarning = 'Không đọc được bộ nhớ trình duyệt; đang dùng dữ liệu mẫu.';
  }
  return createSeed();
}
let state = read();
const listeners = new Set<() => void>();
export const mockService = {
  getSnapshot: () => state,
  subscribe: (listener: () => void) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
  update: (updater: (store: Store) => Store) => {
    const next = updater(state);
    // Original dataset rows never belong in the mutable browser store.
    state = {
      ...next,
      samples: next.samples.filter(
        (sample) => !sample.readOnly && !sample.sourcePath && !sample.id.startsWith('DATA-'),
      ),
    };
    try {
      localStorage.setItem(KEY, JSON.stringify({ version: 3, data: state }));
    } catch {
      storageWarning = 'Bộ nhớ đầy hoặc bị chặn. Thay đổi chỉ được giữ trong phiên này.';
    }
    listeners.forEach((fn) => fn());
  },
  reset: () => {
    mockService.update(() => createSeed());
  },
  warning: () => storageWarning,
};
export const useStore = () =>
  useSyncExternalStore(mockService.subscribe, mockService.getSnapshot, mockService.getSnapshot);
export function audit(actor: string, action: string, target: string) {
  mockService.update((s) => ({
    ...s,
    audits: [
      {
        id: crypto.randomUUID(),
        actor,
        action,
        target,
        time: new Date().toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' }),
      },
      ...s.audits,
    ],
  }));
}
export function download(name: string, value: string, type = 'application/json') {
  const url = URL.createObjectURL(new Blob(['\uFEFF' + value], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

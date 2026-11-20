import { useEffect, useState, useSyncExternalStore } from 'react';
import type { Sample } from '../types';
export interface DatasetCatalog {
  samples: Sample[];
  warnings: string[];
  source: string;
  readOnly: boolean;
  skippedSessions: number;
  scannedAt?: string;
}
export interface SignalPoint {
  t: number;
  phase: string;
  values: Record<string, number | null>;
}
export interface DatasetDetail {
  id: string;
  readOnly: true;
  rowCount: number;
  columns: string[];
  points: SignalPoint[];
  segments: { phase: string; start: number; end: number }[];
  channels: {
    key: string;
    label: string;
    unit: string;
    count: number;
    invalid: number;
    min: number;
    max: number;
    mean: number;
  }[];
  metadata: Record<string, unknown> | null;
  summary: Record<string, unknown> | null;
  prediction: Record<string, unknown> | null;
  sha256: string;
}
type State = { catalog: DatasetCatalog; loading: boolean; error: string };
let state: State = {
  catalog: { samples: [], warnings: [], source: 'data/', readOnly: true, skippedSessions: 0 },
  loading: false,
  error: '',
};
const listeners = new Set<() => void>();
let pending: Promise<void> | null = null;
let initialized = false;
const emit = () => listeners.forEach((fn) => fn());
async function json<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Không đọc được dữ liệu (${response.status}).`);
  if (!response.headers.get('content-type')?.includes('application/json'))
    throw new Error('Chạy bằng npm run dev hoặc npm run preview để kết nối thư mục data/.');
  return response.json();
}
export function refreshDataset(force = true) {
  if (pending) return pending;
  if (force) cache.clear();
  state = { ...state, loading: true, error: '' };
  emit();
  pending = json<DatasetCatalog>(`/api/dataset${force ? '?refresh=1' : ''}`)
    .then((catalog) => {
      state = { catalog, loading: false, error: '' };
      initialized = true;
    })
    .catch((error) => {
      state = { ...state, loading: false, error: error.message || 'Không kết nối được data/.' };
      initialized = true;
    })
    .finally(() => {
      pending = null;
      emit();
    });
  return pending;
}
export function useDataset() {
  const snapshot = useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => {
        listeners.delete(fn);
      };
    },
    () => state,
    () => state,
  );
  useEffect(() => {
    if (!initialized) void refreshDataset(false);
  }, []);
  return snapshot;
}
const cache = new Map<string, DatasetDetail>();
export function useSampleDetail(id: string | null) {
  const revision = useDataset().catalog.scannedAt;
  const [value, setValue] = useState<{
    data: DatasetDetail | null;
    loading: boolean;
    error: string;
  }>({ data: null, loading: false, error: '' });
  useEffect(() => {
    if (!id) {
      setValue({ data: null, loading: false, error: '' });
      return;
    }
    const cached = cache.get(id);
    if (cached) {
      setValue({ data: cached, loading: false, error: '' });
      return;
    }
    const controller = new AbortController();
    setValue({ data: null, loading: true, error: '' });
    json<DatasetDetail>(`/api/dataset/sample?id=${encodeURIComponent(id)}`, controller.signal)
      .then((data) => {
        cache.set(id, data);
        setValue({ data, loading: false, error: '' });
      })
      .catch((error) => {
        if (error.name !== 'AbortError')
          setValue({ data: null, loading: false, error: error.message });
      });
    return () => controller.abort();
  }, [id, revision]);
  return value;
}
export function invalidateDetailCache() {
  cache.clear();
}
export function personName(id: string) {
  return (
    (
      { P001: 'Nguyễn Văn Tài', P002: 'Nguyễn Văn Dương', P003: 'Lưu Hoàng Phúc' } as Record<
        string,
        string
      >
    )[id] ?? 'Chưa ghép hồ sơ / đối chứng'
  );
}

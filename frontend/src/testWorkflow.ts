/** Frontend-only capture state machine. No serial commands or dataset writes. */
export type CapturePhase =
  | 'READY'
  | 'BASELINE'
  | 'WAIT_EXPOSURE'
  | 'EXPOSURE'
  | 'WAIT_RECOVERY'
  | 'RECOVERY'
  | 'WAIT_FINISH'
  | 'COMPLETE'
  | 'ABORTED';
export interface CaptureState {
  phase: CapturePhase;
  elapsed: number;
  startedAt: number | null;
  durations: Record<'BASELINE' | 'EXPOSURE' | 'RECOVERY', number>;
  sampleId: string | null;
}
export type CaptureAction =
  | { type: 'START' | 'EXPOSE' | 'RECOVER' | 'TICK'; now: number }
  | { type: 'FINISH'; sampleId: string }
  | { type: 'ABORT' | 'RESET' };
export function createCaptureState(baseline = 60, exposure = 120, recovery = 60): CaptureState {
  const duration = (n: number, fallback: number) =>
    Number.isFinite(n) && n >= 1 && n <= 86400 ? n : fallback;
  return {
    phase: 'READY',
    elapsed: 0,
    startedAt: null,
    sampleId: null,
    durations: {
      BASELINE: duration(baseline, 60),
      EXPOSURE: duration(exposure, 120),
      RECOVERY: duration(recovery, 60),
    },
  };
}
export function captureBusy(state: CaptureState) {
  return !['READY', 'COMPLETE', 'ABORTED'].includes(state.phase);
}
export function timedPhase(phase: CapturePhase): phase is keyof CaptureState['durations'] {
  return ['BASELINE', 'EXPOSURE', 'RECOVERY'].includes(phase);
}
export function captureReducer(state: CaptureState, action: CaptureAction): CaptureState {
  const start = (phase: CapturePhase, now: number): CaptureState => ({
    ...state,
    phase,
    elapsed: 0,
    startedAt: now,
    sampleId: null,
  });
  if (action.type === 'RESET')
    return { ...state, phase: 'READY', elapsed: 0, startedAt: null, sampleId: null };
  if (action.type === 'ABORT')
    return captureBusy(state)
      ? { ...state, phase: 'ABORTED', elapsed: 0, startedAt: null, sampleId: null }
      : state;
  if (action.type === 'START')
    return ['READY', 'ABORTED'].includes(state.phase) ? start('BASELINE', action.now) : state;
  if (action.type === 'EXPOSE')
    return state.phase === 'WAIT_EXPOSURE' ? start('EXPOSURE', action.now) : state;
  if (action.type === 'RECOVER')
    return state.phase === 'WAIT_RECOVERY' ? start('RECOVERY', action.now) : state;
  if (action.type === 'FINISH')
    return state.phase === 'WAIT_FINISH' && action.sampleId
      ? { ...state, phase: 'COMPLETE', startedAt: null, elapsed: 0, sampleId: action.sampleId }
      : state;
  if (action.type === 'TICK' && timedPhase(state.phase) && state.startedAt !== null) {
    const elapsed = Math.max(0, (action.now - state.startedAt) / 1000);
    const duration = state.durations[state.phase];
    if (elapsed >= duration) {
      const next = {
        BASELINE: 'WAIT_EXPOSURE',
        EXPOSURE: 'WAIT_RECOVERY',
        RECOVERY: 'WAIT_FINISH',
      } as const;
      return { ...state, phase: next[state.phase], elapsed: duration, startedAt: null };
    }
    return { ...state, elapsed };
  }
  return state;
}
export interface TestOutcome {
  kind:
    | 'matched'
    | 'unknown'
    | 'quality_rejected'
    | 'ranked_only'
    | 'no_result'
    | 'unsupported'
    | 'integration_required';
  person: string | null;
  message: string;
  similarity: number | null;
  threshold: number | null;
  margin: number | null;
  marginThreshold: number | null;
}
const finite = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;
export function displayIdentity(value: string) {
  const normalized = value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[đĐ]/g, 'd')
    .toLowerCase()
    .trim();
  return (
    (
      {
        p001: 'Nguyễn Văn Tài',
        tai: 'Nguyễn Văn Tài',
        'nguyen van tai': 'Nguyễn Văn Tài',
        p002: 'Nguyễn Văn Dương',
        duong: 'Nguyễn Văn Dương',
        'nguyen van duong': 'Nguyễn Văn Dương',
        p003: 'Lưu Hoàng Phúc',
        phuc: 'Lưu Hoàng Phúc',
        phucluu: 'Lưu Hoàng Phúc',
        'luu hoang phuc': 'Lưu Hoàng Phúc',
      } as Record<string, string>
    )[normalized] ?? value
  );
}
export function interpretPrediction(value: unknown): TestOutcome {
  const base = {
    person: null,
    similarity: null,
    threshold: null,
    margin: null,
    marginThreshold: null,
  };
  if (!value || typeof value !== 'object')
    return {
      ...base,
      kind: 'no_result',
      message: 'Mẫu chưa có prediction.json. Cần dịch vụ AI để kiểm tra danh tính mới.',
    };
  const file = value as Record<string, unknown>;
  const prediction =
    file.prediction && typeof file.prediction === 'object'
      ? (file.prediction as Record<string, unknown>)
      : {};
  const metrics = {
    similarity: finite(prediction.best_cosine_similarity),
    threshold: finite(prediction.similarity_threshold),
    margin: finite(prediction.margin),
    marginThreshold: finite(prediction.margin_threshold),
  };
  if (file.status === 'quality_rejected')
    return {
      ...base,
      ...metrics,
      kind: 'quality_rejected',
      message:
        'Model đã từ chối chất lượng mẫu. Cần kiểm tra hoặc thu lại, chưa kết luận danh tính.',
    };
  if (file.status === 'identity_rejected')
    return {
      ...base,
      ...metrics,
      kind: 'unknown',
      message: 'Model đã từ chối nhận diện theo ngưỡng. Không có người khớp đủ điều kiện.',
    };
  if (file.status === 'ranked_match_only')
    return {
      ...base,
      ...metrics,
      kind: 'ranked_only',
      message: 'Kết quả chỉ xếp hạng tương đồng, chưa có ngưỡng chấp nhận nên chưa xác nhận người.',
    };
  if (
    file.status === 'identity_accepted' &&
    typeof prediction.person === 'string' &&
    prediction.person.trim() &&
    !['UNKNOWN', 'NULL', 'NONE'].includes(prediction.person.trim().toUpperCase())
  )
    return {
      ...base,
      ...metrics,
      kind: 'matched',
      person: displayIdentity(prediction.person),
      message:
        'Danh tính được model chấp nhận trong kết quả đã lưu. Đây không phải một lần suy luận mới.',
    };
  return {
    ...base,
    ...metrics,
    kind: 'unsupported',
    message:
      'File kết quả chưa có kết luận nhận diện hợp lệ. Không tự dùng nhãn mẫu hoặc best_match làm danh tính.',
  };
}
export function pendingInference(): TestOutcome {
  return {
    kind: 'integration_required',
    person: null,
    similarity: null,
    threshold: null,
    margin: null,
    marginThreshold: null,
    message:
      'Đã hoàn thành thao tác thu thử giao diện. Chưa có raw.csv từ gateway hoặc dịch vụ AI; chưa thể kiểm tra danh tính thật.',
  };
}

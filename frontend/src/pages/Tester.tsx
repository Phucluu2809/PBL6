import { useEffect, useReducer, useState } from 'react';
import {
  Activity,
  ArrowRight,
  BadgeCheck,
  CircleHelp,
  Fingerprint,
  FlaskConical,
  FolderOpen,
  History,
  LockKeyhole,
  Play,
  Radio,
  RotateCcw,
  ScanLine,
  ShieldCheck,
  Square,
  Timer,
  UserRound,
  XCircle,
} from 'lucide-react';
import { useApp } from '../context';
import { useDataset, useSampleDetail, refreshDataset } from '../services/dataset';
import { audit, useStore } from '../services/store';
import {
  captureBusy,
  captureReducer,
  createCaptureState,
  interpretPrediction,
  pendingInference,
  timedPhase,
  type CaptureState,
  type TestOutcome,
} from '../testWorkflow';
import DatasetCharts from '../components/DatasetCharts';
import {
  Avatar,
  Badge,
  Button,
  Confirm,
  Empty,
  Field,
  Notice,
  Panel,
  SearchBox,
} from '../components/ui';

const phaseText: Record<CaptureState['phase'], { title: string; instruction: string }> = {
  READY: {
    title: 'Sẵn sàng kiểm tra',
    instruction: 'Thu mẫu mới hoặc chọn một lượt thu đã có. Không cần chọn trước danh tính.',
  },
  BASELINE: {
    title: 'Đang lấy đường nền',
    instruction: 'Thu tín hiệu nền theo protocol trước khi đưa nguồn mùi cơ thể vào.',
  },
  WAIT_EXPOSURE: {
    title: 'Đưa nguồn mùi vào',
    instruction: 'Chuẩn bị thu trực tiếp mùi cơ thể, sau đó xác nhận để bắt đầu exposure.',
  },
  EXPOSURE: {
    title: 'Đang thu mùi cơ thể',
    instruction: 'Giữ điều kiện thu ổn định. Không chọn vị trí cơ thể hay người dự đoán.',
  },
  WAIT_RECOVERY: {
    title: 'Chuẩn bị phục hồi',
    instruction: 'Xác nhận chuyển sang khí lọc để ghi giai đoạn recovery.',
  },
  RECOVERY: {
    title: 'Đang ghi phục hồi',
    instruction: 'Chờ cảm biến phục hồi theo protocol trước khi kết thúc lượt thu.',
  },
  WAIT_FINISH: {
    title: 'Thu thử đủ các pha',
    instruction: 'Xác nhận hoàn tất để chuyển sang bước kiểm tra danh tính.',
  },
  COMPLETE: {
    title: 'Đã hoàn tất thu thử',
    instruction:
      'Mẫu test chưa biết danh tính. Chọn Kiểm tra danh tính để xem trạng thái bước nhận diện.',
  },
  ABORTED: {
    title: 'Đã hủy lượt thu thử',
    instruction: 'Không có mẫu hoàn chỉnh để nhận diện. Chuẩn bị lại và bắt đầu lượt mới.',
  },
};
const resultTitle: Record<TestOutcome['kind'], string> = {
  matched: 'Đã tìm thấy người khớp',
  unknown: 'Unknown · chưa xác định',
  quality_rejected: 'Cần thu lại mẫu',
  ranked_only: 'Chưa đủ cơ sở kết luận',
  no_result: 'Chưa có kết quả nhận diện',
  unsupported: 'Chưa có kết luận hợp lệ',
  integration_required: 'Chờ kết nối dịch vụ nhận diện',
};
type Attempt = {
  id: string;
  sample: string;
  time: string;
  outcome: TestOutcome;
  source: 'saved' | 'simulator';
};
export default function Tester() {
  const store = useStore();
  const { role, allowed, notify } = useApp();
  const { catalog, loading, error } = useDataset();
  const [source, setSource] = useState<'capture' | 'saved'>('capture');
  const [sampleId, setSampleId] = useState('');
  const [query, setQuery] = useState('');
  const [capture, dispatch] = useReducer(captureReducer, undefined, () =>
    createCaptureState(
      Number(store.settings.baseline),
      Number(store.settings.exposure),
      Number(store.settings.recovery),
    ),
  );
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [history, setHistory] = useState<Attempt[]>([]);
  const [confirmStop, setConfirmStop] = useState(false);
  const detail = useSampleDetail(source === 'saved' && sampleId ? sampleId : null);
  const sample = catalog.samples.find((s) => s.id === sampleId);
  const busy = captureBusy(capture);
  const controls = allowed('testing', 'control');
  const canCheck = allowed('testing', 'create');
  const activeTimed = timedPhase(capture.phase);
  const duration = activeTimed
    ? capture.durations[capture.phase as keyof CaptureState['durations']]
    : 0;
  useEffect(() => {
    if (!timedPhase(capture.phase)) return;
    const timer = setInterval(() => dispatch({ type: 'TICK', now: performance.now() }), 250);
    return () => clearInterval(timer);
  }, [capture.phase]);
  const now = () => performance.now();
  function reset() {
    dispatch({ type: 'RESET' });
    setAttempt(null);
  }
  function switchSource(next: typeof source) {
    if (busy) return;
    setSource(next);
    setAttempt(null);
  }
  function check() {
    if (!canCheck) return;
    if (source === 'capture' && capture.phase !== 'COMPLETE') return;
    if (
      source === 'saved' &&
      (!detail.data || detail.data.id !== sampleId || detail.loading || detail.error)
    )
      return;
    const outcome =
      source === 'capture' ? pendingInference() : interpretPrediction(detail.data?.prediction);
    const item: Attempt = {
      id: crypto.randomUUID(),
      sample:
        source === 'capture' ? (capture.sampleId ?? 'Test sample') : (sample?.name ?? sampleId),
      time: new Date().toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' }),
      outcome,
      source: source === 'capture' ? 'simulator' : 'saved',
    };
    setAttempt(item);
    setHistory((h) => [item, ...h].slice(0, 20));
    audit(
      role,
      source === 'capture'
        ? 'Kiểm tra luồng UI · chưa có suy luận'
        : 'Đọc kết quả nhận diện đã lưu',
      source === 'capture' ? (capture.sampleId ?? 'UI test') : sampleId,
    );
  }
  const readyToCheck =
    source === 'capture'
      ? capture.phase === 'COMPLETE'
      : !!sampleId && detail.data?.id === sampleId && !detail.loading && !detail.error;
  const current = phaseText[capture.phase];
  const progress = duration
    ? Math.min(100, (capture.elapsed / duration) * 100)
    : capture.phase === 'COMPLETE'
      ? 100
      : 0;
  const filtered = catalog.samples.filter(
    (s) =>
      (s.rowCount ?? 0) > 0 &&
      [s.name, s.sourcePath].join(' ').toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <div className="tester-app">
      <div className="tester-heading">
        <div>
          <span className="eyebrow">ROBONOSE / IDENTITY CHECK</span>
          <h1>Thu mùi. Kiểm tra danh tính.</h1>
          <p>Một quy trình dành riêng cho người kiểm tra mẫu.</p>
        </div>
        <Badge tone="purple">
          <ShieldCheck size={13} />
          TESTER WORKSPACE
        </Badge>
      </div>
      <div className="tester-steps" aria-label="Quy trình kiểm tra">
        <div className="active">
          <span>01</span>
          <div>
            <strong>Chuẩn bị mẫu</strong>
            <small>Thu mới hoặc mở lượt đã thu</small>
          </div>
        </div>
        <ArrowRight size={16} />
        <div
          className={
            busy || capture.phase === 'COMPLETE' || (source === 'saved' && sampleId) ? 'active' : ''
          }
        >
          <span>02</span>
          <div>
            <strong>Thu / đọc tín hiệu</strong>
            <small>Mẫu chưa biết danh tính</small>
          </div>
        </div>
        <ArrowRight size={16} />
        <div className={attempt ? 'active' : ''}>
          <span>03</span>
          <div>
            <strong>Kiểm tra danh tính</strong>
            <small>Người khớp hoặc Unknown</small>
          </div>
        </div>
      </div>
      <div className="tester-workspace">
        <section className="tester-console">
          <div className="tester-console-header">
            <div className="tester-source-tabs" role="tablist" aria-label="Nguồn mẫu">
              <button
                role="tab"
                aria-selected={source === 'capture'}
                disabled={busy}
                className={source === 'capture' ? 'active' : ''}
                onClick={() => switchSource('capture')}
              >
                <FlaskConical size={16} />
                Thu mẫu mới
              </button>
              <button
                role="tab"
                aria-selected={source === 'saved'}
                disabled={busy}
                className={source === 'saved' ? 'active' : ''}
                onClick={() => switchSource('saved')}
              >
                <FolderOpen size={16} />
                Mẫu đã thu
              </button>
            </div>
            <Badge tone={source === 'capture' ? 'amber' : 'green'}>
              {source === 'capture' ? 'SIMULATOR' : 'DATA · CHỈ ĐỌC'}
            </Badge>
          </div>
          {source === 'capture' ? (
            <>
              <div className="tester-device">
                <span>
                  <Radio size={16} />
                  ESP32-S3 · chưa kết nối gateway
                </span>
                <small>Thao tác dưới đây chỉ chạy thử giao diện</small>
              </div>
              <div
                className={`odor-scanner ${busy ? 'scanning' : ''} ${capture.phase === 'COMPLETE' ? 'complete' : ''}`}
              >
                <div className="scanner-ring outer" />
                <div className="scanner-ring inner" />
                <Fingerprint size={86} strokeWidth={1.1} />
                <span className="scanner-line" />
                {activeTimed && (
                  <span className="scanner-time">
                    {String(Math.floor(capture.elapsed / 60)).padStart(2, '0')}:
                    {String(Math.floor(capture.elapsed % 60)).padStart(2, '0')}
                  </span>
                )}
              </div>
              <div className="tester-state" aria-live="polite">
                <Badge
                  tone={
                    capture.phase === 'ABORTED'
                      ? 'red'
                      : capture.phase === 'COMPLETE'
                        ? 'green'
                        : 'purple'
                  }
                >
                  {capture.phase}
                </Badge>
                <h2>{current.title}</h2>
                <p>{current.instruction}</p>
              </div>
              <div className="tester-phase-track">
                {(['BASELINE', 'EXPOSURE', 'RECOVERY'] as const).map((p, i) => (
                  <div key={p} className={capture.phase === p ? 'active' : ''}>
                    <span>{i + 1}</span>
                    <strong>{p}</strong>
                    <small>{capture.durations[p]} giây</small>
                  </div>
                ))}
              </div>
              {activeTimed && (
                <div className="tester-timing">
                  <div>
                    <span>
                      {capture.elapsed.toFixed(0)} / {duration} giây
                    </span>
                    <span>Thời gian mô phỏng</span>
                  </div>
                  <div className="progress">
                    <i style={{ width: progress + '%' }} />
                  </div>
                </div>
              )}
              <div className="tester-capture-actions">
                {controls && (
                  <>
                    {['READY', 'ABORTED'].includes(capture.phase) && (
                      <Button
                        onClick={() => {
                          setAttempt(null);
                          dispatch({ type: 'START', now: now() });
                        }}
                      >
                        <Play size={17} />
                        Bắt đầu thu thử giao diện
                      </Button>
                    )}
                    {capture.phase === 'WAIT_EXPOSURE' && (
                      <Button onClick={() => dispatch({ type: 'EXPOSE', now: now() })}>
                        Đã đưa nguồn mùi vào · Expose <ArrowRight size={15} />
                      </Button>
                    )}
                    {capture.phase === 'WAIT_RECOVERY' && (
                      <Button onClick={() => dispatch({ type: 'RECOVER', now: now() })}>
                        Chuyển sang khí lọc · Recover
                      </Button>
                    )}
                    {capture.phase === 'WAIT_FINISH' && (
                      <Button
                        onClick={() =>
                          dispatch({
                            type: 'FINISH',
                            sampleId: `TEST-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
                          })
                        }
                      >
                        Hoàn tất thu thử <BadgeCheck size={16} />
                      </Button>
                    )}
                    {activeTimed && (
                      <Button
                        variant="secondary"
                        onClick={() =>
                          dispatch({ type: 'TICK', now: capture.startedAt! + duration * 1000 })
                        }
                      >
                        Tua đến hết pha demo
                      </Button>
                    )}
                    {busy && (
                      <Button variant="danger" onClick={() => setConfirmStop(true)}>
                        <Square size={14} />
                        Hủy lượt thu thử
                      </Button>
                    )}
                    {capture.phase === 'COMPLETE' && (
                      <Button variant="secondary" onClick={reset}>
                        <RotateCcw size={15} />
                        Lượt mới
                      </Button>
                    )}
                  </>
                )}
                {!controls && (
                  <Notice>
                    Vai trò hiện tại chỉ xem luồng thu; cần quyền Control trên module Ứng dụng kiểm
                    tra mùi để thu thử.
                  </Notice>
                )}
              </div>
              <p className="tester-disclaimer">
                <LockKeyhole size={12} />
                Không mở COM, không bật tải và không ghi mẫu vào data/.
              </p>
            </>
          ) : (
            <div className="tester-saved-input">
              <div className="tester-input-heading">
                <FolderOpen size={25} />
                <div>
                  <h2>Mở một lượt thu có sẵn</h2>
                  <p>Đọc raw.csv và kết quả đã lưu, giữ nguyên file gốc.</p>
                </div>
              </div>
              {error && (
                <Notice tone="amber">
                  {error}
                  <Button variant="ghost" onClick={() => void refreshDataset()}>
                    Thử lại
                  </Button>
                </Notice>
              )}
              <SearchBox
                value={query}
                onChange={setQuery}
                placeholder="Tìm nhãn mẫu hoặc đường dẫn…"
              />
              <Field label="Lượt thu dùng để kiểm tra">
                <select
                  aria-label="Lượt thu kiểm tra"
                  value={sampleId}
                  disabled={loading}
                  onChange={(e) => {
                    setSampleId(e.target.value);
                    setAttempt(null);
                  }}
                >
                  <option value="">{loading ? 'Đang đọc data/…' : 'Chọn một lượt thu…'}</option>
                  {sample && !filtered.some((s) => s.id === sampleId) && (
                    <option value={sample.id}>{sample.name}</option>
                  )}
                  {filtered.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} · {s.date.slice(0, 10)}
                    </option>
                  ))}
                </select>
              </Field>
              <Notice>
                Nhãn lưu trữ chỉ giúp tìm mẫu. Hệ thống không dùng tên file hoặc hồ sơ đã gán để
                quyết định người khớp.
              </Notice>
              {sample ? (
                <>
                  <dl className="tester-input-meta">
                    <div>
                      <dt>Số dòng tín hiệu</dt>
                      <dd>{sample.rowCount}</dd>
                    </div>
                    <div>
                      <dt>Thời lượng</dt>
                      <dd>{sample.duration.toFixed(1)}s</dd>
                    </div>
                    <div>
                      <dt>QC gốc</dt>
                      <dd>{sample.qcSource}</dd>
                    </div>
                  </dl>
                  <DatasetCharts id={sample.id} compact />
                  <details className="tester-source-path">
                    <summary>Nguồn dữ liệu</summary>
                    <code>{sample.sourcePath}</code>
                  </details>
                </>
              ) : (
                <div className="tester-empty-sample">
                  <Activity size={46} strokeWidth={1} />
                  <p>Chọn mẫu để xem tín hiệu trước khi kiểm tra.</p>
                </div>
              )}
            </div>
          )}
          <div className="tester-check-bar">
            <div>
              <ScanLine size={22} />
              <div>
                <strong>Kiểm tra mẫu này là của ai?</strong>
                <small>
                  {source === 'capture'
                    ? 'Chưa nối gateway hoặc dịch vụ AI'
                    : 'Đọc kết luận có trong prediction.json'}
                </small>
              </div>
            </div>
            <Button disabled={!canCheck || !readyToCheck} onClick={check}>
              <Fingerprint size={17} />
              {detail.loading && source === 'saved' ? 'Đang đọc mẫu…' : 'Kiểm tra danh tính'}
            </Button>
          </div>
        </section>
        <aside className="tester-result">
          <div className="tester-result-label">
            <span>KẾT QUẢ KIỂM TRA</span>
            <Badge tone={attempt?.source === 'saved' ? 'green' : 'neutral'}>
              {attempt?.source === 'saved' ? 'FILE ĐÃ LƯU' : 'CHƯA SUY LUẬN MỚI'}
            </Badge>
          </div>
          {attempt ? (
            <>
              <div
                className={`tester-result-symbol ${attempt.outcome.kind === 'matched' ? 'matched' : attempt.outcome.kind === 'unknown' ? 'unknown' : ''}`}
              >
                {attempt.outcome.kind === 'matched' ? (
                  <BadgeCheck size={47} strokeWidth={1.2} />
                ) : attempt.outcome.kind === 'quality_rejected' ? (
                  <XCircle size={47} strokeWidth={1.2} />
                ) : (
                  <CircleHelp size={47} strokeWidth={1.2} />
                )}
              </div>
              <h2>{attempt.outcome.person ?? resultTitle[attempt.outcome.kind]}</h2>
              {attempt.outcome.person && <Badge tone="green">Model đã chấp nhận trong file</Badge>}
              <p>{attempt.outcome.message}</p>
              {attempt.source === 'saved' && (
                <div className="tester-scores">
                  {[
                    ['Cosine similarity', attempt.outcome.similarity],
                    ['Ngưỡng similarity', attempt.outcome.threshold],
                    ['Margin', attempt.outcome.margin],
                    ['Ngưỡng margin', attempt.outcome.marginThreshold],
                  ].map(([label, value]) => (
                    <div key={String(label)}>
                      <span>{label}</span>
                      <strong>{typeof value === 'number' ? value.toFixed(3) : '—'}</strong>
                    </div>
                  ))}
                  <small>Score tương đồng, không phải xác suất.</small>
                </div>
              )}
              <div className="tester-result-source">
                <strong>{attempt.sample}</strong>
                <span>{attempt.time}</span>
                <small>
                  {attempt.source === 'saved'
                    ? 'Nguồn kết luận: prediction.json gốc'
                    : 'Thao tác simulator · chưa sinh raw.csv'}
                </small>
              </div>
              {attempt.source === 'saved' && detail.data?.prediction && (
                <details className="tester-raw-result">
                  <summary>Xem kết quả JSON gốc</summary>
                  <pre className="json-view">{JSON.stringify(detail.data.prediction, null, 2)}</pre>
                </details>
              )}
            </>
          ) : (
            <div className="tester-result-idle">
              <UserRound size={58} strokeWidth={1} />
              <h2>Chờ một mẫu mùi</h2>
              <p>Hoàn tất thu hoặc chọn mẫu có sẵn, rồi bấm Kiểm tra danh tính.</p>
              <div className="tester-result-options">
                <span>
                  <BadgeCheck size={15} />
                  Người khớp
                </span>
                <span>
                  <CircleHelp size={15} />
                  Unknown
                </span>
              </div>
            </div>
          )}
          <div className="tester-known-people">
            <span>HỒ SƠ THAM CHIẾU</span>
            {store.people.map((person) => (
              <div key={person.id}>
                <Avatar name={person.name} small />
                <span>{person.name}</span>
              </div>
            ))}
            <small>Danh sách tham chiếu; không chọn trước người cần nhận diện.</small>
          </div>
        </aside>
      </div>
      <Panel
        title="Các lần kiểm tra trong phiên"
        description="Lịch sử thao tác trên giao diện; không ghi kết quả mới vào dataset"
        actions={<History size={18} />}
      >
        {history.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Thời gian</th>
                  <th>Mẫu</th>
                  <th>Kết luận / trạng thái</th>
                  <th>Nguồn</th>
                </tr>
              </thead>
              <tbody>
                {history.map((item) => (
                  <tr key={item.id}>
                    <td>{item.time}</td>
                    <td>{item.sample}</td>
                    <td>{item.outcome.person ?? resultTitle[item.outcome.kind]}</td>
                    <td>{item.source === 'saved' ? 'prediction.json đã lưu' : 'Thao tác UI'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="tester-history-empty">
            <History size={17} />
            Các lần kiểm tra sẽ xuất hiện tại đây trong phiên này.
          </div>
        )}
      </Panel>
      {confirmStop && (
        <Confirm
          title="Hủy lượt thu thử?"
          description="Lượt simulator đang chạy sẽ kết thúc và không được dùng làm mẫu hoàn chỉnh. Không tác động thiết bị thật."
          onClose={() => setConfirmStop(false)}
          onConfirm={() => {
            dispatch({ type: 'ABORT' });
            setAttempt(null);
            notify('Đã hủy lượt thu thử giao diện.');
          }}
        />
      )}
    </div>
  );
}

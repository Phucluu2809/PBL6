import { useEffect, useState } from 'react';
import {
  Activity,
  Cpu,
  Link2,
  Power,
  Radio,
  SlidersHorizontal,
  Thermometer,
  Droplets,
  RefreshCw,
} from 'lucide-react';
import { useApp } from '../context';
import { audit, mockService, useStore } from '../services/store';
import {
  Badge,
  Button,
  Chart,
  Confirm,
  Field,
  Modal,
  Notice,
  PageTitle,
  Panel,
  Stat,
  Tabs,
} from '../components/ui';
export default function Devices() {
  const { allowed, notify, role } = useApp();
  const [tab, setTab] = useState('Tổng quan thiết bị');
  const [connected, setConnected] = useState(true);
  const [config, setConfig] = useState(false);
  const [port, setPort] = useState('SIMULATOR');
  const [baud, setBaud] = useState('115200');
  const [pump, setPump] = useState(false);
  const [valve, setValve] = useState(false);
  const [pending, setPending] = useState(false);
  const [warmup, setWarmup] = useState(0);
  const [confirm, setConfirm] = useState(false);
  const control = allowed('devices', 'control');
  useEffect(() => {
    if (warmup <= 0 || warmup >= 100) return;
    const timer = setInterval(() => setWarmup((v) => Math.min(100, v + 10)), 350);
    return () => clearInterval(timer);
  }, [warmup]);
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => {
      setPending(false);
      notify('Đã nhận ACK mô phỏng. Không gửi lệnh tới phần cứng.');
    }, 900);
    return () => clearTimeout(timer);
  }, [pending, notify]);
  function command(kind: 'pump' | 'valve') {
    setPending(true);
    if (kind === 'pump') setPump((v) => !v);
    else setValve((v) => !v);
    audit(role, 'Lệnh mô phỏng', kind);
  }
  return (
    <>
      <PageTitle
        eyebrow="THIẾT BỊ / GATEWAY"
        title="Trung tâm thiết bị"
        description="Kết nối, theo dõi tín hiệu và kiểm tra hệ thống cảm biến."
        actions={
          <>
            {control && (
              <Button variant="secondary" onClick={() => setConfig(true)}>
                <SlidersHorizontal size={16} />
                Cấu hình kết nối
              </Button>
            )}
            <Badge tone={connected ? 'green' : 'red'}>
              {connected ? 'Simulator online' : 'Đã ngắt mô phỏng'}
            </Badge>
          </>
        }
      />
      <Notice>
        Chế độ SIMULATOR · Không mở cổng COM, không bật bơm/van thật. Số liệu và ACK đều được mô
        phỏng.
      </Notice>
      <div className="stats-grid">
        <Stat
          label="Gateway"
          value={connected ? 'Online' : 'Offline'}
          detail="Một owner Serial khi tích hợp"
          icon={<Radio size={19} />}
          tone="green"
        />
        <Stat
          label="Tốc độ gói tin"
          value={connected ? '1 Hz' : '0 Hz'}
          detail="5 kênh · không có gói tin thật"
          icon={<Activity size={19} />}
        />
        <Stat
          label="Nhiệt độ"
          value={connected ? '28.4 °C' : '—'}
          detail="BME688 · giá trị mẫu"
          icon={<Thermometer size={19} />}
          tone="amber"
        />
        <Stat
          label="Độ ẩm"
          value={connected ? '64.2 %' : '—'}
          detail="BME688 · giá trị mẫu"
          icon={<Droplets size={19} />}
          tone="blue"
        />
      </div>
      <Tabs
        items={['Tổng quan thiết bị', 'Live monitoring', 'Chẩn đoán', 'Warm-up & điều khiển']}
        value={tab}
        onChange={setTab}
      />
      {tab === 'Tổng quan thiết bị' ? (
        <Panel title="Thiết bị trong workspace" description="01 thiết bị mô phỏng">
          <div className="device-card">
            <div className="device-illustration">
              <Cpu size={68} strokeWidth={1} />
              <span>ESP32-S3</span>
            </div>
            <div className="device-info">
              <Badge tone="purple">DEV KIT · SIMULATOR</Badge>
              <h2>RoboNose S3</h2>
              <p>Gateway thu tín hiệu mùi cơ thể qua USB Serial</p>
              <dl className="detail-grid">
                <div>
                  <dt>Device ID</dt>
                  <dd>RN-S3-001</dd>
                </div>
                <div>
                  <dt>Cổng kết nối</dt>
                  <dd>
                    {port} · {baud} baud
                  </dd>
                </div>
                <div>
                  <dt>Firmware</dt>
                  <dd>Dataset S3 · demo</dd>
                </div>
                <div>
                  <dt>Cảm biến</dt>
                  <dd>4 analog + BME688</dd>
                </div>
              </dl>
              <div className="inline-actions">
                {control && (
                  <Button
                    variant={connected ? 'secondary' : 'primary'}
                    onClick={() => {
                      if (connected) setConfirm(true);
                      else {
                        setConnected(true);
                        notify('Đã kết nối simulator.');
                      }
                    }}
                  >
                    <Link2 size={16} />
                    {connected ? 'Ngắt mô phỏng' : 'Kết nối simulator'}
                  </Button>
                )}
                <Button variant="secondary" onClick={() => setTab('Live monitoring')}>
                  <Activity size={16} />
                  Xem tín hiệu
                </Button>
              </div>
            </div>
          </div>
        </Panel>
      ) : tab === 'Live monitoring' ? (
        <>
          <Panel
            title="Tín hiệu thời gian thực"
            description={
              connected ? 'Tín hiệu mẫu · không phải dữ liệu thiết bị' : 'Mất kết nối mô phỏng'
            }
            actions={
              <Badge tone={connected ? 'green' : 'red'}>
                {connected ? 'SIMULATED' : 'DISCONNECTED'}
              </Badge>
            }
          >
            {connected ? (
              <Chart />
            ) : (
              <div className="empty">
                <Radio />
                <h3>Đang ngắt kết nối</h3>
                <p>Kết nối simulator trong tab Tổng quan thiết bị để xem biểu đồ.</p>
              </div>
            )}
          </Panel>
          <div className="sensor-grid">
            {['TGS2602 · A0', 'MQ3 #1 · A1', 'MQ135 #2 · A2', 'MQ3 #2 · A3', 'BME688 gas'].map(
              (n, i) => (
                <Panel key={n} title={n}>
                  <strong className="sensor-value">
                    {connected ? [1.42, 1.73, 2.16, 1.86, 78.4][i] : '—'}{' '}
                    <small>{i === 4 ? 'kΩ' : 'V'}</small>
                  </strong>
                  <Badge tone={connected ? 'green' : 'red'}>
                    {connected ? 'VALID · Demo' : 'STALE'}
                  </Badge>
                </Panel>
              ),
            )}
          </div>
        </>
      ) : tab === 'Chẩn đoán' ? (
        <Panel
          title="Chẩn đoán cảm biến"
          actions={
            <Button
              variant="secondary"
              onClick={() => notify('Đã làm mới báo cáo chẩn đoán mô phỏng.')}
            >
              <RefreshCw size={14} />
              Làm mới
            </Button>
          }
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Kênh</th>
                  <th>Dữ liệu hợp lệ</th>
                  <th>Khoảng trống lớn nhất</th>
                  <th>Độ ổn định</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {['TGS2602', 'MQ3 #1', 'MQ135 #2', 'MQ3 #2', 'BME688'].map((n, i) => (
                  <tr key={n}>
                    <td>{n}</td>
                    <td>{connected ? '100%' : '—'}</td>
                    <td>{connected ? '1.0s' : '—'}</td>
                    <td>{i === 4 ? 'Đang warm-up' : 'Ổn định (demo)'}</td>
                    <td>
                      <Badge tone={!connected ? 'red' : i === 4 ? 'amber' : 'green'}>
                        {!connected ? 'OFFLINE' : i === 4 ? 'WARMING_UP' : 'HEALTHY'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : (
        <div className="two-columns">
          <Panel title="Warm-up & baseline" description="Mô phỏng tiến trình chuẩn bị cảm biến">
            <p>Giữ protocol và đường khí theo firmware. Không suy ra nồng độ ppm từ TGS2602.</p>
            <div className="progress">
              <i style={{ width: warmup + '%' }} />
            </div>
            <p className="muted">
              {warmup}% ·{' '}
              {warmup === 100 ? 'Sẵn sàng mô phỏng' : warmup ? 'Đang chuẩn bị' : 'Chưa bắt đầu'}
            </p>
            {control && (
              <Button
                disabled={!connected || (warmup > 0 && warmup < 100)}
                onClick={() => setWarmup(10)}
              >
                Chạy warm-up demo
              </Button>
            )}
          </Panel>
          <Panel
            title="Điều khiển đầu ra"
            description="Trạng thái lệnh, không phải phản hồi vị trí van"
          >
            <div className="control-row">
              <span>
                <Power size={18} />
                Bơm · PWM 80%
              </span>
              <Badge tone={pump ? 'green' : 'neutral'}>
                {pending ? 'PENDING' : pump ? 'ON · Demo' : 'OFF · Demo'}
              </Badge>
              {control && (
                <Button
                  variant="secondary"
                  disabled={!connected || pending}
                  onClick={() => command('pump')}
                >
                  Chuyển
                </Button>
              )}
            </div>
            <div className="control-row">
              <span>Đường khí</span>
              <Badge tone="purple">{pending ? 'PENDING' : valve ? 'SAMPLE' : 'FILTERED AIR'}</Badge>
              {control && (
                <Button
                  variant="secondary"
                  disabled={!connected || pending}
                  onClick={() => command('valve')}
                >
                  Chuyển
                </Button>
              )}
            </div>
            <Notice>
              ACK chỉ được giả lập. Sau tích hợp, chờ ACK và trạng thái firmware trước khi hiển thị
              thành công.
            </Notice>
          </Panel>
        </div>
      )}
      {config && (
        <Modal title="Cấu hình kết nối" onClose={() => setConfig(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setConfig(false);
              notify('Đã lưu cấu hình mô phỏng. Không mở Serial.');
            }}
          >
            <Field label="Cổng Serial dự kiến">
              <input value={port} onChange={(e) => setPort(e.target.value)} required />
            </Field>
            <Field label="Baud rate">
              <select value={baud} onChange={(e) => setBaud(e.target.value)}>
                <option>115200</option>
                <option>230400</option>
                <option>460800</option>
              </select>
            </Field>
            <div className="modal-footer">
              <Button type="submit">Lưu cấu hình demo</Button>
            </div>
          </form>
        </Modal>
      )}
      {confirm && (
        <Confirm
          title="Ngắt kết nối mô phỏng?"
          description="Biểu đồ sẽ chuyển sang trạng thái mất kết nối. Không tác động thiết bị thật."
          onConfirm={() => {
            setConnected(false);
            setPump(false);
            setValve(false);
            notify('Đã ngắt simulator.');
          }}
          onClose={() => setConfirm(false)}
        />
      )}
    </>
  );
}
export function Experiments() {
  const s = useStore();
  const { allowed, role, notify } = useApp();
  const [phase, setPhase] = useState('MONITOR');
  const [elapsed, setElapsed] = useState(0);
  const [participant, setParticipant] = useState(s.people.find((p) => p.consent)?.id ?? '');
  const [sampleName, setSampleName] = useState('');
  const [saved, setSaved] = useState(false);
  const [stop, setStop] = useState(false);
  const [creating, setCreating] = useState(false);
  const [active, setActive] = useState(false);
  const control = allowed('experiments', 'control');
  const durations: Record<string, number> = {
    BASELINE: Number(s.settings.baseline),
    EXPOSURE: Number(s.settings.exposure),
    RECOVERY: Number(s.settings.recovery),
  };
  useEffect(() => {
    if (!active || !durations[phase]) return;
    const timer = setInterval(() => setElapsed((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [phase, active]);
  useEffect(() => {
    if (durations[phase] && elapsed >= durations[phase]) {
      setPhase(
        phase === 'BASELINE'
          ? 'WAIT_EXPOSURE'
          : phase === 'EXPOSURE'
            ? 'WAIT_RECOVERY'
            : 'WAIT_FINISH',
      );
      setElapsed(0);
    }
  }, [elapsed, phase]);
  function transition(next: string) {
    setPhase(next);
    setElapsed(0);
    audit(role, `Pha demo: ${next}`, participant);
  }
  const steps = [
    'MONITOR',
    'BASELINE',
    'WAIT_EXPOSURE',
    'EXPOSURE',
    'WAIT_RECOVERY',
    'RECOVERY',
    'WAIT_FINISH',
    'WAIT_NAME',
  ];
  const instruction: Record<string, string> = {
    MONITOR: 'Chuẩn bị đối tượng và tạo phiên mới để bắt đầu.',
    BASELINE: 'Đang ghi baseline qua đầu lấy mẫu.',
    WAIT_EXPOSURE: 'Đặt mẫu rồi chọn Expose. Hệ thống không tự chuyển pha.',
    EXPOSURE: 'Đang ghi đáp ứng cảm biến với mẫu.',
    WAIT_RECOVERY: 'Chọn Recover để chuyển sang khí lọc.',
    RECOVERY: 'Đang ghi phục hồi qua khí lọc.',
    WAIT_FINISH: 'Chọn Finish hoặc kéo dài recovery.',
    WAIT_NAME: 'Đặt tên và lưu mẫu trước khi sang lượt tiếp theo.',
    ERROR: 'Phiên đã dừng khẩn cấp trong mô phỏng.',
  };
  return (
    <>
      <PageTitle
        eyebrow="VẬN HÀNH / THU MẪU"
        title="Không gian thí nghiệm"
        description="Theo dõi quy trình thu mẫu với các bước chờ thao tác rõ ràng."
        actions={
          control && (
            <Button onClick={() => setCreating(true)} disabled={active}>
              <FlaskIcon />
              Tạo thí nghiệm
            </Button>
          )
        }
      />
      <Notice>
        Phiên mô phỏng · đồng hồ chạy theo thời gian thật trên trình duyệt. Không kết nối phần cứng,
        không ghi raw.csv.
      </Notice>
      <Panel
        title={active ? `Phiên ${participant} · mùi cơ thể trực tiếp` : 'Chưa có phiên đang chạy'}
        description="Protocol S3 · baseline / exposure / recovery"
        actions={<Badge tone={phase === 'ERROR' ? 'red' : 'purple'}>{phase}</Badge>}
      >
        <div className="phase-steps">
          {steps.map((p, i) => (
            <div
              key={p}
              className={p === phase ? 'current' : steps.indexOf(phase) > i ? 'done' : ''}
            >
              <span>{i + 1}</span>
              <small>{p}</small>
            </div>
          ))}
        </div>
        <div className="experiment-status">
          <div>
            <small>TRẠNG THÁI HIỆN TẠI</small>
            <h2>{phase.replaceAll('_', ' ')}</h2>
            <p>{instruction[phase]}</p>
          </div>
          <div className="timer">
            {String(Math.floor(elapsed / 60)).padStart(2, '0')}
            <span>:</span>
            {String(elapsed % 60).padStart(2, '0')}
            <small>{durations[phase] ? `/ ${durations[phase]} giây` : 'Chờ thao tác'}</small>
          </div>
        </div>
        {durations[phase] && (
          <div className="progress">
            <i style={{ width: Math.min(100, (elapsed / durations[phase]) * 100) + '%' }} />
          </div>
        )}
        <div className="inline-actions">
          {control && active && (
            <>
              {phase === 'MONITOR' && (
                <Button onClick={() => transition('BASELINE')}>Start baseline</Button>
              )}
              {phase === 'WAIT_EXPOSURE' && (
                <Button onClick={() => transition('EXPOSURE')}>Expose · Đã đặt mẫu</Button>
              )}
              {phase === 'WAIT_RECOVERY' && (
                <Button onClick={() => transition('RECOVERY')}>Recover · Khí lọc</Button>
              )}
              {phase === 'WAIT_FINISH' && (
                <>
                  <Button onClick={() => transition('WAIT_NAME')}>Finish</Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      transition('RECOVERY');
                      setElapsed(Math.max(0, Number(s.settings.recovery) - 30));
                    }}
                  >
                    Thêm 30s recovery
                  </Button>
                </>
              )}
              {durations[phase] && (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setElapsed(durations[phase]);
                    notify('Đã tua tới cuối pha mô phỏng.');
                  }}
                >
                  Tua demo tới hết pha
                </Button>
              )}
              {phase === 'WAIT_NAME' && saved && (
                <Button
                  onClick={() => {
                    setActive(false);
                    setPhase('MONITOR');
                    setSaved(false);
                    setSampleName('');
                  }}
                >
                  Next · Lượt tiếp theo
                </Button>
              )}
              {phase !== 'ERROR' && (
                <Button variant="danger" onClick={() => setStop(true)}>
                  Dừng khẩn cấp demo
                </Button>
              )}
            </>
          )}
          {phase === 'ERROR' && control && (
            <Button
              variant="secondary"
              onClick={() => {
                setPhase('MONITOR');
                setActive(false);
              }}
            >
              Về trạng thái chuẩn bị
            </Button>
          )}
        </div>
      </Panel>
      <div className="dashboard-columns">
        <Panel title="Tín hiệu phiên đo" description="Dữ liệu đường cong minh họa">
          <Chart />
        </Panel>
        <Panel title="Thông tin vận hành">
          <dl className="detail-list">
            <div>
              <dt>Người giữ quyền điều khiển</dt>
              <dd>{control ? role : 'Chỉ xem'}</dd>
            </div>
            <div>
              <dt>Thiết bị</dt>
              <dd>RN-S3-001 · Simulator</dd>
            </div>
            <div>
              <dt>Protocol</dt>
              <dd>
                {s.settings.baseline}s / {s.settings.exposure}s / {s.settings.recovery}s
              </dd>
            </div>
            <div>
              <dt>Bơm trong phiên demo</dt>
              <dd>{active && phase !== 'ERROR' ? 'PWM 80% · mô phỏng' : 'OFF'}</dd>
            </div>
            <div>
              <dt>Đường khí</dt>
              <dd>
                {['RECOVERY', 'WAIT_FINISH', 'WAIT_NAME', 'ERROR'].includes(phase)
                  ? 'FILTERED AIR'
                  : 'SAMPLE'}
              </dd>
            </div>
          </dl>
          {phase === 'WAIT_NAME' && control && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (saved) return;
                const id = `S-${crypto.randomUUID().slice(0, 8)}`;
                mockService.update((v) => ({
                  ...v,
                  samples: [
                    {
                      id,
                      person: participant,
                      name: sampleName,
                      date: new Date().toISOString(),
                      qc: 'REVIEW',
                      duration:
                        Number(s.settings.baseline) +
                        Number(s.settings.exposure) +
                        Number(s.settings.recovery),
                      device: 'RN-S3-001',
                      protocol: `S3 · ${s.settings.baseline} / ${s.settings.exposure} / ${s.settings.recovery}`,
                      note: sampleName,
                    },
                    ...v.samples,
                  ],
                }));
                setSaved(true);
                audit(role, 'Lưu mẫu mô phỏng', id);
                notify('Đã lưu metadata mẫu demo. Chưa có dữ liệu tín hiệu thật.');
              }}
            >
              <Field label="Tên mẫu sau khi finish">
                <input
                  required
                  value={sampleName}
                  disabled={saved}
                  onChange={(e) => setSampleName(e.target.value)}
                  placeholder="Tên mẫu…"
                />
              </Field>
              <Button type="submit" disabled={saved}>
                {saved ? 'Đã lưu · QC REVIEW' : 'Lưu mẫu demo'}
              </Button>
            </form>
          )}
        </Panel>
      </div>
      {creating && (
        <Modal title="Tạo thí nghiệm mô phỏng" onClose={() => setCreating(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!s.people.some((p) => p.id === participant && p.consent)) return;
              setCreating(false);
              setActive(true);
              setSaved(false);
              setPhase('MONITOR');
              setElapsed(0);
              notify('Đã tạo phiên demo. Chọn Start baseline để thu mẫu.');
            }}
          >
            <Field label="Đối tượng đã đồng ý tham gia">
              <select required value={participant} onChange={(e) => setParticipant(e.target.value)}>
                <option value="">Chọn hồ sơ đã xác nhận đồng ý…</option>
                {s.people
                  .filter((p) => p.consent)
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.id} · {p.name}
                    </option>
                  ))}
              </select>
            </Field>
            <Notice>
              Thu trực tiếp mùi cơ thể, không phân chia vị trí lấy mẫu. Nếu chưa có đối tượng đủ
              điều kiện, xác nhận tại mục Hồ sơ nhận diện trước.
            </Notice>
            <Notice>
              Protocol: {s.settings.baseline}s → {s.settings.exposure}s → {s.settings.recovery}s.
              Các bước WAIT cần xác nhận thủ công.
            </Notice>
            <div className="modal-footer">
              <Button
                type="submit"
                disabled={!participant || !s.people.some((p) => p.id === participant && p.consent)}
              >
                Tạo phiên mô phỏng
              </Button>
            </div>
          </form>
        </Modal>
      )}
      {stop && (
        <Confirm
          title="Dừng khẩn cấp phiên demo?"
          description="Phiên sẽ chuyển ERROR và đầu ra mô phỏng chuyển OFF. Không gửi lệnh OFF tới thiết bị thật."
          onConfirm={() => {
            transition('ERROR');
            notify('Đã dừng phiên mô phỏng.');
          }}
          onClose={() => setStop(false)}
        />
      )}
    </>
  );
}
function FlaskIcon() {
  return <Activity size={16} />;
}

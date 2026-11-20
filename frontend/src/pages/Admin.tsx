import { useState } from 'react';
import {
  Download,
  Save,
  Shield,
  RefreshCw,
  CheckCircle2,
  Server,
  Database,
  Radio,
  HardDrive,
  FileText,
  Plus,
} from 'lucide-react';
import { roles, modules, actions, isStore, upgradePermissions } from '../domain';
import type { Role, Permission } from '../types';
import { useStore, mockService, audit, download } from '../services/store';
import { useDataset } from '../services/dataset';
import { useApp } from '../context';
import {
  Avatar,
  Badge,
  Button,
  Chart,
  Confirm,
  Empty,
  Field,
  Modal,
  Notice,
  PageTitle,
  Panel,
  SearchBox,
  Select,
  Stat,
  Tabs,
} from '../components/ui';
const moduleLabels: Record<string, string> = {
  testing: 'Ứng dụng kiểm tra mùi',
  dashboard: 'Tổng quan',
  devices: 'Thiết bị',
  experiments: 'Thí nghiệm',
  samples: 'Thư viện mẫu',
  people: 'Người tham gia',
  ai: 'AI & nhận diện',
  models: 'Model Registry',
  users: 'Người dùng',
  roles: 'Phân quyền',
  security: 'Bảo mật',
  settings: 'Cài đặt',
  reports: 'Báo cáo',
  profile: 'Hồ sơ cá nhân',
};
function ApiTokens() {
  const s = useStore();
  const { role, allowed, notify } = useApp();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [scope, setScope] = useState('samples:view');
  const [expiry, setExpiry] = useState('2026-12-17');
  const [revoking, setRevoking] = useState<string | null>(null);
  type DemoToken = { id: string; name: string; scope: string; expiry: string; revoked: boolean };
  let tokens: DemoToken[] = [];
  try {
    const parsed = JSON.parse(s.settings.demoTokens ?? '[]');
    if (Array.isArray(parsed))
      tokens = parsed.filter(
        (t) =>
          typeof t.id === 'string' &&
          typeof t.name === 'string' &&
          typeof t.scope === 'string' &&
          typeof t.expiry === 'string' &&
          typeof t.revoked === 'boolean',
      );
  } catch {}
  function save(next: DemoToken[]) {
    mockService.update((v) => ({
      ...v,
      settings: { ...v.settings, demoTokens: JSON.stringify(next) },
    }));
  }
  return (
    <>
      <Notice>
        Token dưới đây chỉ là metadata mô phỏng. Không tạo khóa truy cập thật và không thể dùng để
        xác thực API.
      </Notice>
      <Panel
        title="API tokens"
        description="Quản lý phạm vi và thời hạn token minh họa"
        actions={
          allowed('security', 'manage') && (
            <Button onClick={() => setCreating(true)}>
              <Plus size={15} />
              Tạo token demo
            </Button>
          )
        }
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Tên token</th>
                <th>Phạm vi</th>
                <th>Hết hạn</th>
                <th>Trạng thái</th>
                <th>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {tokens.map((t) => (
                <tr key={t.id}>
                  <td>
                    <strong>{t.name}</strong>
                    <small className="cell-sub">
                      demo_{t.id.slice(0, 8)}… · không phải khóa API
                    </small>
                  </td>
                  <td>{t.scope}</td>
                  <td>{t.expiry}</td>
                  <td>
                    <Badge tone={t.revoked ? 'red' : 'purple'}>
                      {t.revoked ? 'Đã thu hồi' : 'Demo'}
                    </Badge>
                  </td>
                  <td>
                    {allowed('security', 'manage') && (
                      <Button
                        variant="ghost"
                        disabled={t.revoked}
                        onClick={() => setRevoking(t.id)}
                      >
                        Thu hồi
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!tokens.length && (
          <Empty
            title="Chưa có token demo"
            description="Tạo metadata token để xem thử luồng quản trị."
          />
        )}
      </Panel>
      {creating && (
        <Modal title="Tạo metadata token" onClose={() => setCreating(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              save([
                ...tokens,
                { id: crypto.randomUUID(), name: name.trim(), scope, expiry, revoked: false },
              ]);
              audit(role, 'Tạo metadata token demo', name);
              setName('');
              setCreating(false);
              notify('Đã lưu metadata token, không phát hành khóa thật.');
            }}
          >
            <Field label="Tên token">
              <input required value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Phạm vi">
              <select value={scope} onChange={(e) => setScope(e.target.value)}>
                <option>samples:view</option>
                <option>samples:export</option>
                <option>devices:view</option>
              </select>
            </Field>
            <Field label="Ngày hết hạn">
              <input
                type="date"
                required
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
              />
            </Field>
            <div className="modal-footer">
              <Button type="submit">Tạo token demo</Button>
            </div>
          </form>
        </Modal>
      )}
      {revoking && (
        <Confirm
          title="Thu hồi token demo?"
          description="Thay đổi trạng thái metadata token minh họa."
          onClose={() => setRevoking(null)}
          onConfirm={() => {
            save(tokens.map((t) => (t.id === revoking ? { ...t, revoked: true } : t)));
            audit(role, 'Thu hồi token demo', revoking);
            notify('Đã thu hồi metadata token demo.');
          }}
        />
      )}
    </>
  );
}
export function Roles() {
  const s = useStore();
  const { role, allowed, notify } = useApp();
  const [selected, setSelected] = useState<Role>('Operator');
  const [pending, setPending] = useState<{
    module: (typeof modules)[number];
    action: Permission;
  } | null>(null);
  return (
    <>
      <PageTitle
        eyebrow="QUẢN TRỊ / PHÂN QUYỀN"
        title="Vai trò & quyền truy cập"
        description="Thiết kế quyền theo module và hành động cho từng nhóm người dùng."
      />
      <Notice>
        Ma trận này điều khiển giao diện demo. Backend cần triển khai RBAC độc lập. Vai trò Super
        Admin được giữ cố định trong bản demo.
      </Notice>
      <div className="role-cards">
        {roles.map((r) => (
          <button
            className={`role-card ${selected === r ? 'selected' : ''}`}
            key={r}
            onClick={() => setSelected(r)}
          >
            <Shield size={20} />
            <strong>{r}</strong>
            <small>{s.users.filter((u) => u.roles.includes(r)).length} người dùng</small>
          </button>
        ))}
      </div>
      <Panel
        title={`Ma trận quyền · ${selected}`}
        description="Quyền hiệu lực của tài khoản nhiều vai trò là hợp các quyền đã gán."
        actions={
          <Badge tone="purple">
            {selected === 'Super Admin' ? 'Vai trò hệ thống' : 'Có thể cấu hình'}
          </Badge>
        }
      >
        <div className="table-scroll">
          <table className="permission-table">
            <thead>
              <tr>
                <th>Module</th>
                {actions.map((a) => (
                  <th key={a}>{a}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {modules.map((m) => (
                <tr key={m}>
                  <td>
                    <strong>{moduleLabels[m]}</strong>
                  </td>
                  {actions.map((a) => (
                    <td key={a}>
                      <input
                        type="checkbox"
                        aria-label={`${selected} ${moduleLabels[m]} ${a}`}
                        checked={s.permissions[selected][m].includes(a)}
                        disabled={
                          !allowed('roles', 'manage') ||
                          selected === 'Super Admin' ||
                          (role !== 'Super Admin' && selected === 'Admin')
                        }
                        onChange={() => setPending({ module: m, action: a })}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      {pending && (
        <Confirm
          title="Cập nhật quyền truy cập?"
          description={`${selected} · ${moduleLabels[pending.module]} · ${pending.action}. Sidebar và nút thao tác sẽ thay đổi theo cấu hình này.`}
          onClose={() => setPending(null)}
          onConfirm={() => {
            mockService.update((v) => {
              const current = v.permissions[selected][pending.module];
              const enabled = current.includes(pending.action);
              let next = enabled
                ? current.filter((a) => a !== pending.action)
                : [...current, pending.action];
              if (!enabled && pending.action !== 'view' && !next.includes('view'))
                next.push('view');
              if (enabled && pending.action === 'view') next = [];
              return {
                ...v,
                permissions: {
                  ...v.permissions,
                  [selected]: { ...v.permissions[selected], [pending.module]: next },
                },
              };
            });
            audit(
              role,
              'Cập nhật ma trận quyền',
              `${selected}.${pending.module}.${pending.action}`,
            );
            notify('Đã lưu ma trận quyền demo.');
          }}
        />
      )}
    </>
  );
}
export function Security() {
  const s = useStore();
  const { allowed, role, notify } = useApp();
  const [tab, setTab] = useState('Audit logs');
  const [query, setQuery] = useState('');
  const [confirm, setConfirm] = useState<string | null>(null);
  const [policy, setPolicy] = useState({ ...s.settings });
  const logs = s.audits.filter((a) =>
    (a.actor + a.action + a.target).toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      <PageTitle
        eyebrow="QUẢN TRỊ / BẢO MẬT"
        title="Trung tâm bảo mật"
        description="Theo dõi hoạt động, phiên truy cập và chính sách của workspace."
      />
      <Tabs
        items={['Audit logs', 'Lịch sử đăng nhập', 'Phiên hệ thống', 'Chính sách', 'API tokens']}
        value={tab}
        onChange={setTab}
      />
      {tab === 'Audit logs' ? (
        <Panel
          title="Nhật ký hoạt động"
          description="Các thao tác trên dữ liệu demo được ghi tự động"
          actions={
            allowed('security', 'export') && (
              <Button
                variant="secondary"
                onClick={() => download('audit-demo.json', JSON.stringify(logs, null, 2))}
              >
                <Download size={15} />
                Xuất nhật ký
              </Button>
            )
          }
        >
          <div className="table-toolbar">
            <SearchBox
              value={query}
              onChange={setQuery}
              placeholder="Tìm người thao tác, hành động, đối tượng…"
            />
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Thời gian</th>
                  <th>Người thực hiện</th>
                  <th>Hành động</th>
                  <th>Đối tượng</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((a) => (
                  <tr key={a.id}>
                    <td className="nowrap">{a.time}</td>
                    <td>{a.actor}</td>
                    <td>{a.action}</td>
                    <td>{a.target}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!logs.length && <Empty />}
        </Panel>
      ) : tab === 'Chính sách' ? (
        <Panel title="Chính sách bảo mật">
          <form
            className="settings-form"
            onSubmit={(e) => {
              e.preventDefault();
              mockService.update((v) => ({ ...v, settings: { ...v.settings, ...policy } }));
              audit(role, 'Cập nhật chính sách', 'security');
              notify('Đã lưu chính sách demo. Chưa áp dụng xác thực thật.');
            }}
          >
            <Notice>
              Cấu hình chỉ lưu để xem trước. Không thực thi kiểm tra mật khẩu, timeout hoặc MFA.
            </Notice>
            <div className="form-grid">
              <Field label="Độ dài mật khẩu tối thiểu">
                <input
                  type="number"
                  min="8"
                  max="128"
                  required
                  value={policy.passwordLength}
                  onChange={(e) => setPolicy({ ...policy, passwordLength: e.target.value })}
                />
              </Field>
              <Field label="Timeout phiên (phút)">
                <input
                  type="number"
                  min="5"
                  max="1440"
                  required
                  value={policy.sessionTimeout}
                  onChange={(e) => setPolicy({ ...policy, sessionTimeout: e.target.value })}
                />
              </Field>
            </div>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={policy.requireMfa === 'true'}
                onChange={(e) => setPolicy({ ...policy, requireMfa: String(e.target.checked) })}
              />
              Yêu cầu MFA cho tài khoản quản trị
            </label>
            {allowed('security', 'manage') && (
              <Button type="submit">
                <Save size={15} />
                Lưu chính sách demo
              </Button>
            )}
          </form>
        </Panel>
      ) : tab === 'API tokens' ? (
        <ApiTokens />
      ) : (
        <Panel title={tab} description="Danh sách phiên minh họa, không phải phiên xác thực thật">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Người dùng</th>
                  <th>Thiết bị / IP</th>
                  <th>Thời gian</th>
                  <th>Trạng thái</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {s.users
                  .filter((u) => u.status === 'Active')
                  .slice(0, 5)
                  .map((u, i) => (
                    <tr key={u.id}>
                      <td>
                        <div className="person-cell">
                          <Avatar name={u.name} small />
                          <strong>{u.name}</strong>
                        </div>
                      </td>
                      <td>
                        Chrome · Windows
                        <small className="cell-sub">192.0.2.{10 + i} · IP minh họa</small>
                      </td>
                      <td>{u.lastLogin}</td>
                      <td>
                        <Badge
                          tone={
                            s.settings['revoked-' + u.id]
                              ? 'red'
                              : i === 3 && tab === 'Lịch sử đăng nhập'
                                ? 'amber'
                                : 'green'
                          }
                        >
                          {s.settings['revoked-' + u.id]
                            ? 'Đã thu hồi demo'
                            : i === 3 && tab === 'Lịch sử đăng nhập'
                              ? 'Thất bại · Demo'
                              : 'Thành công · Demo'}
                        </Badge>
                      </td>
                      <td>
                        {allowed('security', 'manage') && tab === 'Phiên hệ thống' && (
                          <Button
                            variant="ghost"
                            disabled={!!s.settings['revoked-' + u.id]}
                            onClick={() => setConfirm(u.id)}
                          >
                            Thu hồi phiên
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      {confirm && (
        <Confirm
          title="Thu hồi phiên mô phỏng?"
          description="Không làm mất phiên đăng nhập thật. Thao tác được lưu trong audit demo."
          onClose={() => setConfirm(null)}
          onConfirm={() => {
            mockService.update((v) => ({
              ...v,
              settings: { ...v.settings, ['revoked-' + confirm]: 'true' },
            }));
            audit(role, 'Thu hồi phiên demo', confirm);
            notify('Đã thu hồi phiên mô phỏng.');
          }}
        />
      )}
    </>
  );
}
export function Settings() {
  const s = useStore();
  const { role, allowed, notify } = useApp();
  const [tab, setTab] = useState('Cài đặt chung');
  const [form, setForm] = useState({ ...s.settings });
  const [reset, setReset] = useState(false);
  const [restore, setRestore] = useState(false);
  const [restoring, setRestoring] = useState('');
  const editable = allowed('settings', 'manage');
  const fields =
    tab === 'Cài đặt chung'
      ? [
          ['labName', 'Tên phòng lab'],
          ['email', 'Email liên hệ'],
          ['timezone', 'Múi giờ'],
          ['language', 'Ngôn ngữ'],
        ]
      : tab === 'Protocol thí nghiệm'
        ? [
            ['baseline', 'Thời lượng baseline (giây)'],
            ['exposure', 'Thời lượng exposure (giây)'],
            ['recovery', 'Thời lượng recovery (giây)'],
          ]
        : tab === 'Lưu trữ'
          ? [
              ['auditRetention', 'Giữ audit (ngày)'],
              ['sampleRetention', 'Giữ dữ liệu mẫu (ngày)'],
            ]
          : [['email', 'Email nhận thông báo']];
  return (
    <>
      <PageTitle
        eyebrow="WORKSPACE / HỆ THỐNG"
        title="Cài đặt hệ thống"
        description="Cấu hình không gian làm việc và tham số nghiên cứu mặc định."
      />
      <Tabs
        items={[
          'Cài đặt chung',
          'Protocol thí nghiệm',
          'Thông báo',
          'Sao lưu & khôi phục',
          'Lưu trữ',
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === 'Sao lưu & khôi phục' ? (
        <Panel title="Dữ liệu demo trên trình duyệt">
          <Notice>
            Backup chỉ chứa dữ liệu mô phỏng của giao diện. Không sao lưu database hoặc file đo
            thật.
          </Notice>
          <div className="backup-cards">
            <div>
              <Database size={28} />
              <h3>Xuất bản sao demo</h3>
              <p>Tải JSON của workspace hiện tại để lưu cục bộ.</p>
              <Button
                variant="secondary"
                onClick={() =>
                  download(
                    'robonose-demo-backup.json',
                    JSON.stringify({ version: 3, data: s }, null, 2),
                  )
                }
              >
                <Download size={15} />
                Tải backup JSON
              </Button>
            </div>
            {editable && (
              <div>
                <RefreshCw size={28} />
                <h3>Khôi phục & đặt lại</h3>
                <p>Khôi phục backup giao diện hoặc nạp bộ dữ liệu ban đầu.</p>
                <div className="inline-actions">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setRestore(true);
                      setRestoring('');
                    }}
                  >
                    Khôi phục JSON
                  </Button>
                  <Button variant="danger" onClick={() => setReset(true)}>
                    Đặt lại demo
                  </Button>
                </div>
              </div>
            )}
          </div>
        </Panel>
      ) : (
        <Panel title={tab} description="Thay đổi chỉ áp dụng cho workspace demo">
          <form
            className="settings-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!editable) return;
              mockService.update((v) => ({ ...v, settings: { ...v.settings, ...form } }));
              audit(role, 'Lưu cấu hình', tab);
              notify('Đã lưu cấu hình demo.');
            }}
          >
            {tab === 'Protocol thí nghiệm' && (
              <Notice>
                Luôn giữ các bước WAIT để người vận hành xác nhận. Thông số này chỉ dùng cho phiên
                mô phỏng mới; chưa cấu hình firmware.
              </Notice>
            )}
            {tab === 'Lưu trữ' && (
              <Notice>
                Giá trị chỉ là cấu hình giao diện. Demo không tự xóa dữ liệu theo thời hạn.
              </Notice>
            )}
            <div className="form-grid">
              {fields.map(([key, label]) => (
                <Field label={label} key={key}>
                  <input
                    disabled={!editable}
                    required
                    value={form[key]}
                    type={
                      [
                        'baseline',
                        'exposure',
                        'recovery',
                        'auditRetention',
                        'sampleRetention',
                      ].includes(key)
                        ? 'number'
                        : key === 'email'
                          ? 'email'
                          : 'text'
                    }
                    min="1"
                    max="86400"
                    onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  />
                </Field>
              ))}
            </div>
            {tab === 'Thông báo' && (
              <>
                <label className="checkbox-label">
                  <input
                    disabled={!editable}
                    type="checkbox"
                    checked={form.notifications === 'true'}
                    onChange={(e) => setForm({ ...form, notifications: String(e.target.checked) })}
                  />
                  Bật cảnh báo thiết bị và phiên đo
                </label>
                <Notice>
                  Chưa gửi email hoặc thông báo đẩy. Kênh thông báo sẽ nối backend sau.
                </Notice>
              </>
            )}
            {editable && (
              <Button type="submit">
                <Save size={16} />
                Lưu thay đổi
              </Button>
            )}
          </form>
        </Panel>
      )}
      {reset && (
        <Confirm
          title="Đặt lại toàn bộ dữ liệu demo?"
          description="Xóa các thay đổi user, mẫu, model và cấu hình cục bộ; khôi phục bộ dữ liệu ban đầu."
          onClose={() => setReset(false)}
          onConfirm={() => {
            mockService.reset();
            setForm({ ...mockService.getSnapshot().settings });
            notify('Đã khôi phục dữ liệu demo ban đầu.');
          }}
        />
      )}
      {restore && (
        <Modal title="Khôi phục backup demo" onClose={() => setRestore(false)}>
          <Notice>Backup sẽ thay thế toàn bộ dữ liệu demo trên trình duyệt.</Notice>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              try {
                const parsed = JSON.parse(restoring);
                const d =
                  parsed.version === 2
                    ? { ...parsed.data, permissions: upgradePermissions(parsed.data?.permissions) }
                    : parsed.data;
                if (
                  ![2, 3].includes(parsed.version) ||
                  !isStore(d) ||
                  !Array.isArray(d?.users) ||
                  !Array.isArray(d?.samples) ||
                  !Array.isArray(d?.people) ||
                  !Array.isArray(d?.models) ||
                  !Array.isArray(d?.audits) ||
                  !Array.isArray(d?.invitations) ||
                  !Array.isArray(d?.results) ||
                  !d?.permissions ||
                  !d?.settings ||
                  !roles.every((r) => modules.every((m) => Array.isArray(d.permissions[r]?.[m])))
                )
                  throw new Error('invalid');
                mockService.update(() => d);
                setForm({ ...d.settings });
                setRestore(false);
                notify('Đã khôi phục dữ liệu demo.');
              } catch {
                notify('Backup không hợp lệ. Hãy dùng JSON xuất từ giao diện này.');
              }
            }}
          >
            <Field label="Nội dung file JSON backup">
              <textarea
                rows={8}
                required
                value={restoring}
                onChange={(e) => setRestoring(e.target.value)}
              />
            </Field>
            <div className="modal-footer">
              <Button type="submit" variant="danger">
                Xác nhận thay thế dữ liệu
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
export function Health() {
  const { notify } = useApp();
  const [tab, setTab] = useState('System health');
  return (
    <>
      <PageTitle
        eyebrow="HỆ THỐNG / GIÁM SÁT"
        title="Trạng thái hệ thống"
        description="Kiểm tra các thành phần và theo dõi sự kiện vận hành."
        actions={
          <Button variant="secondary" onClick={() => notify('Đã làm mới trạng thái minh họa.')}>
            <RefreshCw size={15} />
            Làm mới
          </Button>
        }
      />
      <Notice>
        Chưa kết nối backend. Các thành phần bên dưới có trạng thái dự kiến cho môi trường phát
        triển.
      </Notice>
      <Tabs items={['System health', 'Nhật ký lỗi & sự kiện']} value={tab} onChange={setTab} />
      {tab === 'System health' ? (
        <div className="cards-grid">
          {[
            [Server, 'Backend API', 'Chưa tích hợp', 'REST / WebSocket'],
            [Database, 'Database', 'Chưa tích hợp', 'PostgreSQL dự kiến'],
            [Radio, 'Device Gateway', 'Simulator', 'Không mở cổng COM'],
            [HardDrive, 'Bộ nhớ trình duyệt', 'Sẵn sàng', 'localStorage · dữ liệu demo'],
          ].map(([Icon, label, status, detail]) => {
            const I = Icon as typeof Server;
            return (
              <Panel key={String(label)}>
                <div className="health-card">
                  <I size={25} />
                  <h2>{String(label)}</h2>
                  <Badge
                    tone={
                      status === 'Sẵn sàng'
                        ? 'green'
                        : status === 'Simulator'
                          ? 'purple'
                          : 'neutral'
                    }
                  >
                    {String(status)}
                  </Badge>
                  <p className="muted">{String(detail)}</p>
                </div>
              </Panel>
            );
          })}
        </div>
      ) : (
        <Panel title="Sự kiện phát triển">
          <div className="list-row">
            <Badge tone="purple">INFO</Badge>
            <span>Frontend khởi tạo ở chế độ mô phỏng.</span>
            <small>Workspace local</small>
          </div>
          <div className="list-row">
            <Badge tone="amber">NOTICE</Badge>
            <span>Backend và Serial chưa được kết nối.</span>
            <small>Chưa có log thiết bị thật</small>
          </div>
        </Panel>
      )}
    </>
  );
}
export function Reports() {
  const s = useStore();
  const { catalog, loading, error } = useDataset();
  const { allowed } = useApp();
  const [tab, setTab] = useState('Thí nghiệm');
  const [range, setRange] = useState('Toàn bộ dữ liệu');
  const sampleRows =
    range === 'Toàn bộ dữ liệu'
      ? catalog.samples
      : catalog.samples.filter((v) => v.date.startsWith(range));
  return (
    <>
      <PageTitle
        eyebrow="PHÂN TÍCH / BÁO CÁO"
        title="Báo cáo workspace"
        description={
          loading
            ? 'Đang đọc danh mục dữ liệu gốc…'
            : 'Tổng hợp lượt thu gốc, nhận diện và hoạt động quản trị.'
        }
        actions={
          <>
            <Select
              label="Khoảng thời gian"
              value={range}
              onChange={setRange}
              options={[
                'Toàn bộ dữ liệu',
                ...new Set(catalog.samples.map((v) => v.date.slice(0, 10)).filter(Boolean)),
              ]}
            />
            {allowed('reports', 'export') && (
              <Button
                variant="secondary"
                onClick={() =>
                  download(
                    'robonose-report.json',
                    JSON.stringify(
                      {
                        type: tab,
                        range,
                        samples: sampleRows.length,
                        pass: sampleRows.filter((v) => v.qc === 'PASS').length,
                        ...(tab === 'Nhận diện' && allowed('ai') ? { aiResults: s.results } : {}),
                        ...(tab === 'Quản trị' && allowed('users')
                          ? { users: s.users.length, audits: s.audits }
                          : {}),
                      },
                      null,
                      2,
                    ),
                  )
                }
              >
                <Download size={16} />
                Xuất báo cáo
              </Button>
            )}
          </>
        }
      />
      <Tabs
        items={[
          'Thí nghiệm',
          ...(allowed('ai') ? ['Nhận diện'] : []),
          ...(allowed('users') ? ['Quản trị'] : []),
        ]}
        value={tab}
        onChange={setTab}
      />
      {error && <Notice tone="amber">{error}</Notice>}
      {tab === 'Thí nghiệm' ? (
        <>
          <div className="stats-grid">
            <Stat
              label="Mẫu trong khoảng"
              value={sampleRows.length}
              detail={range}
              icon={<FileText size={18} />}
            />
            <Stat
              label="QC PASS"
              value={sampleRows.filter((v) => v.qc === 'PASS').length}
              detail="Chỉ đếm kết luận PASS có trong dữ liệu gốc"
              icon={<CheckCircle2 size={18} />}
              tone="green"
            />
            <Stat
              label="QC REVIEW"
              value={sampleRows.filter((v) => v.qc === 'REVIEW').length}
              detail="Chờ đánh giá thủ công"
              icon={<FileText size={18} />}
              tone="amber"
            />
            <Stat
              label="QC FAIL"
              value={sampleRows.filter((v) => v.qc === 'FAIL').length}
              detail="Cần kiểm tra phiên"
              icon={<FileText size={18} />}
              tone="red"
            />
          </div>
          <Panel title="Phân bố mẫu theo đối tượng">
            <div className="bar-chart">
              {s.people.map((p) => (
                <div key={p.id}>
                  <span>{p.id}</span>
                  <div>
                    <i
                      style={{
                        width: `${(sampleRows.filter((v) => v.person === p.id).length / Math.max(1, ...s.people.map((x) => sampleRows.filter((v) => v.person === x.id).length))) * 100}%`,
                      }}
                    />
                  </div>
                  <strong>{sampleRows.filter((v) => v.person === p.id).length}</strong>
                </div>
              ))}
            </div>
          </Panel>
        </>
      ) : tab === 'Nhận diện' ? (
        <Panel title="Kết quả AI mô phỏng">
          {s.results.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Mẫu</th>
                    <th>Loại</th>
                    <th>Kết quả</th>
                    <th>Model</th>
                  </tr>
                </thead>
                <tbody>
                  {s.results.map((r) => (
                    <tr key={r.id}>
                      <td>{r.sample}</td>
                      <td>{r.kind}</td>
                      <td>{r.result}</td>
                      <td>{r.model}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="Chưa có kết quả AI"
              description="Tạo kết quả mô phỏng tại AI & nhận diện."
            />
          )}
        </Panel>
      ) : (
        <Panel title="Tổng hợp quản trị">
          <Notice>Bản tổng hợp chỉ có dữ liệu demo của trình duyệt.</Notice>
          <div className="bar-chart">
            {roles.map((r) => (
              <div key={r}>
                <span>{r}</span>
                <div>
                  <i
                    style={{
                      width:
                        (s.users.filter((u) => u.roles.includes(r)).length / s.users.length) * 100 +
                        '%',
                    }}
                  />
                </div>
                <strong>{s.users.filter((u) => u.roles.includes(r)).length}</strong>
              </div>
            ))}
          </div>
          <p className="padded muted">
            {s.audits.length} sự kiện audit ·{' '}
            {s.invitations.filter((i) => i.status === 'Pending').length} lời mời đang chờ.
          </p>
        </Panel>
      )}
    </>
  );
}

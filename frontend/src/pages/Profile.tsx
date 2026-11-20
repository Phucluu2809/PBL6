import { useState } from 'react';
import { Activity, ArrowRight, KeyRound, ShieldCheck, Save } from 'lucide-react';
import { useStore, mockService, audit } from '../services/store';
import { useApp } from '../context';
import { roles } from '../domain';
import type { Role } from '../types';
import {
  Avatar,
  Badge,
  Button,
  Confirm,
  Field,
  Notice,
  PageTitle,
  Panel,
  Tabs,
} from '../components/ui';
export function Login({ onLogin }: { onLogin: (r: Role) => void }) {
  const [role, setRole] = useState<Role>('Tester');
  const [tab, setTab] = useState('Đăng nhập demo');
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  return (
    <div className="login-layout">
      <div className="login-story">
        <div className="brand">
          <span className="brand-icon">
            <Activity size={26} />
          </span>
          <span>
            robonose<span className="brand-label">BIOID WORKSPACE</span>
          </span>
        </div>
        <div>
          <span className="eyebrow">A NEW SENSE OF IDENTITY</span>
          <h1>
            Mỗi tín hiệu.
            <br />
            Một dấu ấn riêng.
          </h1>
          <p>
            Không gian dành cho nghiên cứu mùi cơ thể, từ thu thập tín hiệu đến khám phá nhận diện.
          </p>
          <div className="login-wave" aria-hidden="true">
            {Array.from({ length: 42 }, (_, i) => (
              <i key={i} style={{ height: Math.sin(i * 0.4) ** 2 * 95 + 18 + 'px' }} />
            ))}
          </div>
        </div>
        <small>RoboNose Research Lab · PBL6</small>
      </div>
      <div className="login-form-area">
        <div className="login-form">
          <Badge tone="purple">FRONTEND PREVIEW</Badge>
          <h2>{tab === 'Đăng nhập demo' ? 'Chào mừng trở lại' : tab}</h2>
          <p>Khám phá workspace với dữ liệu mùi cơ thể gốc ở chế độ chỉ đọc.</p>
          <Tabs
            items={['Đăng nhập demo', 'Quên mật khẩu']}
            value={tab === 'Đặt lại mật khẩu' ? 'Quên mật khẩu' : tab}
            onChange={(t) => {
              setTab(t);
              setSent(false);
            }}
          />
          {tab === 'Đăng nhập demo' ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                onLogin(role);
              }}
            >
              <Field label="Vai trò xem trước">
                <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
                  {roles.map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </Field>
              <Notice>
                Không cần tài khoản hay mật khẩu thật. Vai trò này chỉ thay đổi quyền trên giao diện
                demo.
              </Notice>
              <Button type="submit">
                Vào workspace <ArrowRight size={17} />
              </Button>
            </form>
          ) : tab === 'Quên mật khẩu' ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setSent(true);
              }}
            >
              <Field label="Email minh họa">
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                />
              </Field>
              <Button type="submit">Xem trước yêu cầu reset</Button>
              {sent && (
                <div className="notice green">
                  <span>
                    Đã mô phỏng yêu cầu. Không gửi email, chưa tạo token reset.
                    <button
                      className="text-link"
                      onClick={() => setTab('Đặt lại mật khẩu')}
                      type="button"
                    >
                      Xem form đặt lại
                    </button>
                  </span>
                </div>
              )}
            </form>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setSent(true);
              }}
            >
              <Notice>
                Form minh họa, không có token xác thực. Không nhập mật khẩu đang dùng.
              </Notice>
              <Field label="Mật khẩu mẫu mới">
                <input type="password" minLength={8} required autoComplete="new-password" />
              </Field>
              <Button type="submit">Xem trước đặt lại</Button>
              {sent && <p className="muted">Đã hoàn tất minh họa. Mật khẩu không được lưu.</p>}
            </form>
          )}
          <small className="login-footer">
            Giao diện phục vụ tích hợp backend · Không xác thực danh tính thật
          </small>
        </div>
      </div>
    </div>
  );
}
export default function Profile() {
  const s = useStore();
  const { role, notify } = useApp();
  const user = s.users.find((u) => u.roles.includes(role)) ?? s.users[0];
  const [tab, setTab] = useState('Hồ sơ cá nhân');
  const [form, setForm] = useState({ ...user });
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);
  return (
    <>
      <PageTitle
        eyebrow="TÀI KHOẢN / CÁ NHÂN"
        title="Tài khoản của tôi"
        description="Hồ sơ, tùy chọn bảo mật và phiên đăng nhập minh họa."
      />
      <Tabs items={['Hồ sơ cá nhân', 'Bảo mật', 'Phiên đăng nhập']} value={tab} onChange={setTab} />
      {tab === 'Hồ sơ cá nhân' ? (
        <Panel title="Thông tin cá nhân">
          <div className="user-detail-heading">
            <Avatar name={user.name} />
            <div>
              <h2>{user.name}</h2>
              <p>{user.email}</p>
            </div>
            <Badge tone="purple">{role}</Badge>
          </div>
          <form
            className="settings-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!form.name.trim()) {
                notify('Vui lòng nhập họ tên.');
                return;
              }
              mockService.update((v) => ({
                ...v,
                users: v.users.map((u) =>
                  u.id === form.id
                    ? {
                        ...u,
                        name: form.name.trim(),
                        phone: form.phone,
                        department: form.department,
                        title: form.title,
                      }
                    : u,
                ),
              }));
              audit(role, 'Cập nhật hồ sơ demo', user.id);
              notify('Đã lưu hồ sơ demo.');
            }}
          >
            <div className="form-grid">
              <Field label="Họ và tên">
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="Email">
                <input readOnly value={form.email} />
              </Field>
              <Field label="Điện thoại">
                <input
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                />
              </Field>
              <Field label="Phòng ban">
                <input
                  value={form.department}
                  onChange={(e) => setForm({ ...form, department: e.target.value })}
                />
              </Field>
              <Field label="Chức danh">
                <input
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                />
              </Field>
              <Field label="Ngôn ngữ">
                <select>
                  <option>Tiếng Việt</option>
                </select>
              </Field>
            </div>
            <Button type="submit">
              <Save size={16} />
              Lưu hồ sơ
            </Button>
          </form>
        </Panel>
      ) : tab === 'Bảo mật' ? (
        <div className="two-columns">
          <Panel title="Đổi mật khẩu · giao diện mẫu">
            <form
              className="settings-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (password !== confirmPassword) {
                  setError('Mật khẩu xác nhận chưa khớp.');
                  return;
                }
                setPassword('');
                setConfirmPassword('');
                setError('');
                notify('Đã kiểm tra form mẫu. Không lưu hoặc thay đổi mật khẩu thật.');
              }}
            >
              <Notice>Không nhập mật khẩu thật. Chưa kết nối dịch vụ xác thực.</Notice>
              <Field label="Mật khẩu mẫu mới">
                <input
                  required
                  type="password"
                  minLength={8}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </Field>
              <Field label="Nhập lại mật khẩu mẫu">
                <input
                  required
                  type="password"
                  minLength={8}
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </Field>
              {error && (
                <p role="alert" className="form-error">
                  {error}
                </p>
              )}
              <Button type="submit">
                <KeyRound size={15} />
                Kiểm tra form mẫu
              </Button>
            </form>
          </Panel>
          <Panel title="Xác thực hai bước">
            <div className="padded">
              <ShieldCheck size={30} />
              <h3>MFA · {user.mfa ? 'Đã bật demo' : 'Chưa bật demo'}</h3>
              <p className="muted">
                Đổi trạng thái minh họa. Chưa có QR enrollment hoặc recovery codes thật.
              </p>
              <Button variant="secondary" onClick={() => setConfirm(true)}>
                {user.mfa ? 'Tắt MFA demo' : 'Bật MFA demo'}
              </Button>
            </div>
          </Panel>
        </div>
      ) : (
        <Panel title="Phiên đăng nhập của tôi">
          <div className="list-row">
            <div>
              <strong>Chrome · Windows</strong>
              <p className="muted">127.0.0.1 · phiên demo của trình duyệt này</p>
            </div>
            <Badge tone="green">Hiện tại · Demo</Badge>
          </div>
          <Notice>
            Chưa có danh sách phiên xác thực thật. Dùng Đăng xuất demo trong sidebar để thoát
            workspace.
          </Notice>
        </Panel>
      )}
      {confirm && (
        <Confirm
          title="Đổi trạng thái MFA demo?"
          description="Chỉ thay đổi dữ liệu hiển thị. Không cấu hình xác thực hai bước thật."
          onClose={() => setConfirm(false)}
          onConfirm={() => {
            mockService.update((v) => ({
              ...v,
              users: v.users.map((u) => (u.id === user.id ? { ...u, mfa: !u.mfa } : u)),
            }));
            audit(role, 'Đổi trạng thái MFA demo', user.id);
            notify('Đã cập nhật MFA demo.');
          }}
        />
      )}
    </>
  );
}

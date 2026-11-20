import { useState, type FormEvent } from 'react';
import {
  Plus,
  Users as UsersIcon,
  UserCheck,
  ShieldCheck,
  Mail,
  Pencil,
  LockKeyhole,
  UnlockKeyhole,
  UserX,
  ChevronLeft,
  ChevronRight,
  Eye,
  Send,
  RotateCcw,
} from 'lucide-react';
import { useStore, mockService, audit, download } from '../services/store';
import { roles, validateUser, csvCell } from '../domain';
import type { Role, User, UserStatus } from '../types';
import { useApp } from '../context';
import {
  Avatar,
  Badge,
  Button,
  Confirm,
  DownloadButton,
  Empty,
  Field,
  Modal,
  PageTitle,
  Panel,
  SearchBox,
  Select,
  Stat,
  Tabs,
  statusTone,
  Notice,
} from '../components/ui';
const statusLabel: Record<UserStatus, string> = {
  Active: 'Hoạt động',
  Locked: 'Đã khóa',
  Disabled: 'Vô hiệu hóa',
  Pending: 'Chờ kích hoạt',
};
export default function Users() {
  const store = useStore();
  const { allowed, role, notify } = useApp();
  const [tab, setTab] = useState('Tất cả người dùng');
  const [query, setQuery] = useState('');
  const [groupFilter, setGroupFilter] = useState('Tất cả nhóm');
  const [roleFilter, setRoleFilter] = useState('Tất cả vai trò');
  const [statusFilter, setStatusFilter] = useState('Tất cả trạng thái');
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<User | null | undefined>(undefined);
  const [viewing, setViewing] = useState<User | null>(null);
  const [detailTab, setDetailTab] = useState('Thông tin');
  const [confirm, setConfirm] = useState<{
    title: string;
    description: string;
    action: () => void;
  } | null>(null);
  const [invite, setInvite] = useState(false);
  const manage = allowed('users', 'manage');
  const filtered = store.users.filter(
    (u) =>
      (groupFilter === 'Tất cả nhóm' || u.group === groupFilter) &&
      (u.name + ' ' + u.email + ' ' + u.id).toLowerCase().includes(query.toLowerCase()) &&
      (roleFilter === 'Tất cả vai trò' || u.roles.includes(roleFilter as Role)) &&
      (statusFilter === 'Tất cả trạng thái' || statusLabel[u.status] === statusFilter),
  );
  const pages = Math.max(1, Math.ceil(filtered.length / 8));
  const current = Math.min(page, pages);
  const rows = filtered.slice((current - 1) * 8, current * 8);
  function changeStatus(user: User, status: UserStatus) {
    setConfirm({
      title: `${statusLabel[status]} tài khoản?`,
      description: `Thay đổi trạng thái của ${user.name} (${user.email}). Thao tác chỉ tác động dữ liệu demo trên trình duyệt.`,
      action: () => {
        mockService.update((s) => ({
          ...s,
          users: s.users.map((u) => (u.id === user.id ? { ...u, status } : u)),
        }));
        audit(role, `Trạng thái: ${statusLabel[status]}`, user.id);
        notify('Đã cập nhật trạng thái tài khoản.');
      },
    });
  }
  function save(user: User) {
    if (!manage) return;
    mockService.update((s) => ({
      ...s,
      users: s.users.some((u) => u.id === user.id)
        ? s.users.map((u) => (u.id === user.id ? user : u))
        : [user, ...s.users],
    }));
    audit(role, editing ? 'Cập nhật tài khoản' : 'Tạo tài khoản', user.id);
    setEditing(undefined);
    notify('Đã lưu tài khoản vào dữ liệu demo.');
  }
  const protectedUser = (u: User) => u.roles.includes('Super Admin');
  return (
    <>
      <PageTitle
        eyebrow="WORKSPACE / QUẢN TRỊ"
        title="Quản lý người dùng"
        description="Quản lý thành viên và quyền truy cập trong không gian nghiên cứu."
        actions={
          <>
            {allowed('users', 'export') && (
              <DownloadButton
                onClick={() =>
                  download(
                    'robonose-users.csv',
                    [
                      ['Mã', 'Họ tên', 'Email', 'Vai trò', 'Trạng thái'].map(csvCell).join(','),
                      ...filtered.map((u) =>
                        [u.id, u.name, u.email, u.roles.join(';'), u.status].map(csvCell).join(','),
                      ),
                    ].join('\n'),
                    'text/csv;charset=utf-8',
                  )
                }
              />
            )}
            {manage && (
              <Button onClick={() => setEditing(null)}>
                <Plus size={17} />
                Thêm người dùng
              </Button>
            )}
          </>
        }
      />
      <div className="stats-grid">
        <Stat
          label="Tổng người dùng"
          value={store.users.length}
          detail="Thành viên trong workspace"
          icon={<UsersIcon size={19} />}
        />
        <Stat
          label="Đang hoạt động"
          value={store.users.filter((u) => u.status === 'Active').length}
          detail="Tài khoản có thể truy cập"
          icon={<UserCheck size={19} />}
          tone="green"
        />
        <Stat
          label="Đã bật MFA"
          value={store.users.filter((u) => u.mfa).length}
          detail="Bảo mật xác thực hai bước"
          icon={<ShieldCheck size={19} />}
          tone="blue"
        />
        <Stat
          label="Lời mời đang chờ"
          value={store.invitations.filter((i) => i.status === 'Pending').length}
          detail="Chờ thành viên chấp nhận"
          icon={<Mail size={19} />}
          tone="amber"
        />
      </div>
      <Panel>
        <div className="table-tabs">
          <Tabs
            items={['Tất cả người dùng', 'Lời mời', 'Nhóm người dùng']}
            value={tab}
            onChange={(t) => {
              setTab(t);
              setPage(1);
            }}
          />
          {manage && (
            <Button variant="secondary" onClick={() => setInvite(true)}>
              <Send size={14} />
              Mời thành viên
            </Button>
          )}
        </div>
        {tab === 'Tất cả người dùng' ? (
          <>
            <div className="table-toolbar">
              <SearchBox
                value={query}
                onChange={(v) => {
                  setQuery(v);
                  setPage(1);
                }}
                placeholder="Tìm theo tên, email hoặc mã người dùng…"
              />
              <div className="filters">
                <Select
                  label="Lọc nhóm"
                  value={groupFilter}
                  onChange={(v) => {
                    setGroupFilter(v);
                    setPage(1);
                  }}
                  options={['Tất cả nhóm', 'Nhóm nghiên cứu', 'Nhóm vận hành']}
                />
                <Select
                  label="Lọc vai trò"
                  value={roleFilter}
                  onChange={(v) => {
                    setRoleFilter(v);
                    setPage(1);
                  }}
                  options={['Tất cả vai trò', ...roles]}
                />
                <Select
                  label="Lọc trạng thái"
                  value={statusFilter}
                  onChange={(v) => {
                    setStatusFilter(v);
                    setPage(1);
                  }}
                  options={['Tất cả trạng thái', ...Object.values(statusLabel)]}
                />
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Người dùng</th>
                    <th>Vai trò</th>
                    <th>Trạng thái</th>
                    <th>Bảo mật</th>
                    <th>Đăng nhập gần nhất</th>
                    <th className="align-right">Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <button
                          className="person-cell"
                          onClick={() => {
                            setViewing(user);
                            setDetailTab('Thông tin');
                          }}
                        >
                          <Avatar name={user.name} />
                          <span>
                            <strong>{user.name}</strong>
                            <small>{user.email}</small>
                          </span>
                        </button>
                      </td>
                      <td>
                        <div className="role-tags">
                          {user.roles.map((r) => (
                            <span
                              className={`role-tag ${r === 'Super Admin' || r === 'Admin' ? 'admin' : ''}`}
                              key={r}
                            >
                              {r}
                            </span>
                          ))}
                        </div>
                        <small className="cell-sub">{user.department}</small>
                      </td>
                      <td>
                        <Badge tone={statusTone(user.status)}>{statusLabel[user.status]}</Badge>
                      </td>
                      <td>
                        <span className={`mfa ${user.mfa ? 'enabled' : ''}`}>
                          <ShieldCheck size={14} />
                          {user.mfa ? 'Đã bật MFA' : 'Chưa bật'}
                        </span>
                      </td>
                      <td className="muted nowrap">{user.lastLogin}</td>
                      <td>
                        <div className="row-actions">
                          <button
                            aria-label={`Xem ${user.name}`}
                            title="Xem chi tiết"
                            onClick={() => {
                              setViewing(user);
                              setDetailTab('Thông tin');
                            }}
                          >
                            <Eye size={16} />
                          </button>
                          {manage && !protectedUser(user) && (
                            <>
                              <button
                                aria-label={`Sửa ${user.name}`}
                                title="Sửa tài khoản"
                                onClick={() => setEditing(user)}
                              >
                                <Pencil size={15} />
                              </button>
                              <button
                                aria-label={`${user.status === 'Locked' ? 'Mở khóa' : 'Khóa'} ${user.name}`}
                                title={user.status === 'Locked' ? 'Mở khóa' : 'Khóa tài khoản'}
                                onClick={() =>
                                  changeStatus(user, user.status === 'Locked' ? 'Active' : 'Locked')
                                }
                              >
                                {user.status === 'Locked' ? (
                                  <UnlockKeyhole size={15} />
                                ) : (
                                  <LockKeyhole size={15} />
                                )}
                              </button>
                              <button
                                aria-label={`${user.status === 'Disabled' ? 'Kích hoạt' : 'Vô hiệu hóa'} ${user.name}`}
                                title={user.status === 'Disabled' ? 'Kích hoạt' : 'Vô hiệu hóa'}
                                onClick={() =>
                                  changeStatus(
                                    user,
                                    user.status === 'Disabled' ? 'Active' : 'Disabled',
                                  )
                                }
                              >
                                <UserX size={15} />
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!rows.length && <Empty />}
            <div className="pagination">
              <span>
                Hiển thị {filtered.length ? (current - 1) * 8 + 1 : 0}–
                {Math.min(current * 8, filtered.length)} trong {filtered.length} người dùng
              </span>
              <div>
                <Button
                  variant="secondary small-button"
                  disabled={current === 1}
                  onClick={() => setPage(current - 1)}
                >
                  <ChevronLeft size={15} />
                </Button>
                {Array.from({ length: pages }, (_, i) => (
                  <button
                    key={i}
                    className={`page-number ${current === i + 1 ? 'active' : ''}`}
                    onClick={() => setPage(i + 1)}
                  >
                    {i + 1}
                  </button>
                ))}
                <Button
                  variant="secondary small-button"
                  disabled={current === pages}
                  onClick={() => setPage(current + 1)}
                >
                  <ChevronRight size={15} />
                </Button>
              </div>
            </div>
          </>
        ) : tab === 'Lời mời' ? (
          <>
            <Notice>Email không được gửi trong bản demo. Lời mời chỉ lưu trên trình duyệt.</Notice>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Vai trò</th>
                    <th>Trạng thái</th>
                    <th>Ngày mời</th>
                    <th>Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {store.invitations.map((i) => (
                    <tr key={i.id}>
                      <td>{i.email}</td>
                      <td>{i.role}</td>
                      <td>
                        <Badge tone={statusTone(i.status)}>{i.status}</Badge>
                      </td>
                      <td>{i.date}</td>
                      <td>
                        {manage && i.status === 'Pending' && (
                          <div className="inline-actions">
                            <Button
                              variant="ghost"
                              onClick={() => {
                                audit(role, 'Gửi lại lời mời demo', i.email);
                                notify('Đã mô phỏng gửi lại lời mời. Không gửi email thật.');
                              }}
                            >
                              <RotateCcw size={14} />
                              Gửi lại
                            </Button>
                            <Button
                              variant="ghost"
                              onClick={() =>
                                setConfirm({
                                  title: 'Thu hồi lời mời?',
                                  description: i.email,
                                  action: () => {
                                    mockService.update((s) => ({
                                      ...s,
                                      invitations: s.invitations.map((v) =>
                                        v.id === i.id ? { ...v, status: 'Revoked' } : v,
                                      ),
                                    }));
                                    audit(role, 'Thu hồi lời mời', i.email);
                                    notify('Đã thu hồi lời mời.');
                                  },
                                })
                              }
                            >
                              Thu hồi
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="cards-grid padded">
            {['Nhóm nghiên cứu', 'Nhóm vận hành'].map((group) => (
              <div className="group-card" key={group}>
                <UsersIcon size={24} />
                <h3>{group}</h3>
                <p>{store.users.filter((u) => u.group === group).length} thành viên</p>
                <div className="avatar-stack">
                  {store.users
                    .filter((u) => u.group === group)
                    .map((u) => (
                      <Avatar key={u.id} name={u.name} small />
                    ))}
                </div>
                <p className="muted">Gán nhóm cho thành viên trong form sửa tài khoản.</p>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setTab('Tất cả người dùng');
                    setQuery('');
                    setRoleFilter('Tất cả vai trò');
                    setStatusFilter('Tất cả trạng thái');
                    setGroupFilter(group);
                    setPage(1);
                  }}
                >
                  Xem thành viên
                </Button>
              </div>
            ))}
          </div>
        )}
      </Panel>
      <div className="footnote">
        <ShieldCheck size={14} />
        Quyền trên giao diện được mô phỏng. Backend cần kiểm tra quyền khi tích hợp.
      </div>
      {editing !== undefined && (
        <UserForm
          user={editing}
          users={store.users}
          onClose={() => setEditing(undefined)}
          onSave={save}
        />
      )}
      {viewing && (
        <Modal title="Chi tiết người dùng" wide onClose={() => setViewing(null)}>
          <div className="user-detail-heading">
            <Avatar name={viewing.name} />
            <div>
              <h2>{viewing.name}</h2>
              <p>{viewing.email}</p>
            </div>
            <Badge tone={statusTone(viewing.status)}>{statusLabel[viewing.status]}</Badge>
          </div>
          <Tabs
            items={['Thông tin', 'Vai trò & nhóm', 'Phiên đăng nhập', 'Lịch sử', 'Bảo mật']}
            value={detailTab}
            onChange={setDetailTab}
          />
          {detailTab === 'Thông tin' ? (
            <dl className="detail-grid">
              {Object.entries({
                'Mã người dùng': viewing.id,
                'Phòng ban': viewing.department,
                'Chức danh': viewing.title,
                'Điện thoại': viewing.phone || 'Chưa cập nhật',
                'Đăng nhập gần nhất': viewing.lastLogin,
                Email: viewing.email,
              }).map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          ) : detailTab === 'Vai trò & nhóm' ? (
            <div className="padded">
              <p>Vai trò: {viewing.roles.join(', ')}</p>
              <p>Nhóm: {viewing.group}</p>
              <p className="muted">Quyền hiệu lực là hợp các quyền của những vai trò đã gán.</p>
              <div className="permission-list">
                {Object.entries(store.permissions[viewing.roles[0]]).map(([m]) => (
                  <div key={m}>
                    <strong>{m}</strong>
                    <span>
                      {Array.from(
                        new Set(
                          viewing.roles.flatMap(
                            (r) =>
                              store.permissions[r][m as keyof (typeof store.permissions)[Role]],
                          ),
                        ),
                      ).join(', ') || 'Không có quyền'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : detailTab === 'Lịch sử' ? (
            <div className="padded">
              {store.audits
                .filter((a) => a.target === viewing.id)
                .map((a) => (
                  <p key={a.id}>
                    {a.time} · {a.action}
                  </p>
                ))}
              {!store.audits.some((a) => a.target === viewing.id) && (
                <Empty title="Chưa có hoạt động" />
              )}
            </div>
          ) : detailTab === 'Phiên đăng nhập' ? (
            <div className="padded">
              <p>
                Chrome · Windows · 127.0.0.1 <Badge tone="purple">Phiên mô phỏng</Badge>
              </p>
              {manage && (
                <Button
                  variant="secondary"
                  onClick={() => {
                    audit(role, 'Thu hồi phiên demo', viewing.id);
                    notify('Đã ghi yêu cầu thu hồi phiên mô phỏng.');
                  }}
                >
                  Thu hồi phiên demo
                </Button>
              )}
            </div>
          ) : (
            <div className="padded">
              <p>MFA: {viewing.mfa ? 'Đã bật' : 'Chưa bật'}</p>
              {manage && !protectedUser(viewing) && (
                <div className="inline-actions">
                  <Button
                    variant="secondary"
                    onClick={() =>
                      setConfirm({
                        title: 'Reset MFA?',
                        description: `Đặt lại trạng thái MFA demo của ${viewing.name}.`,
                        action: () => {
                          mockService.update((s) => ({
                            ...s,
                            users: s.users.map((u) =>
                              u.id === viewing.id ? { ...u, mfa: false } : u,
                            ),
                          }));
                          setViewing({ ...viewing, mfa: false });
                          audit(role, 'Reset MFA', viewing.id);
                          notify('Đã reset MFA demo.');
                        },
                      })
                    }
                  >
                    Reset MFA
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      audit(role, 'Yêu cầu đổi mật khẩu demo', viewing.id);
                      notify('Đã ghi yêu cầu đổi mật khẩu mô phỏng.');
                    }}
                  >
                    Yêu cầu đổi mật khẩu
                  </Button>
                </div>
              )}
            </div>
          )}
        </Modal>
      )}
      {invite && <InviteForm onClose={() => setInvite(false)} />}
      {confirm && (
        <Confirm
          title={confirm.title}
          description={confirm.description}
          onConfirm={confirm.action}
          onClose={() => setConfirm(null)}
        />
      )}
    </>
  );
}
function UserForm({
  user,
  users,
  onSave,
  onClose,
}: {
  user: User | null;
  users: User[];
  onSave: (u: User) => void;
  onClose: () => void;
}) {
  const { role } = useApp();
  const [form, setForm] = useState<User>(
    user ?? {
      id: `USR-${crypto.randomUUID().slice(0, 8)}`,
      name: '',
      email: '',
      department: 'Nghiên cứu',
      title: 'Thành viên',
      phone: '',
      roles: ['Viewer'],
      status: 'Active',
      mfa: false,
      lastLogin: '—',
      group: 'Nhóm nghiên cứu',
    },
  );
  const [error, setError] = useState('');
  const update = (key: keyof User, value: unknown) => setForm((f) => ({ ...f, [key]: value }));
  function submit(e: FormEvent) {
    e.preventDefault();
    const error = validateUser(form, users, user?.id);
    if (error) {
      setError(error);
      return;
    }
    if (role !== 'Super Admin' && form.roles.includes('Super Admin')) {
      setError('Chỉ Super Admin có thể cấp vai trò này.');
      return;
    }
    onSave({ ...form, name: form.name.trim(), email: form.email.trim().toLowerCase() });
  }
  return (
    <Modal title={user ? 'Chỉnh sửa tài khoản' : 'Thêm người dùng'} onClose={onClose}>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Họ và tên *">
            <input
              required
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
              placeholder="Nguyễn Văn A"
              maxLength={100}
            />
          </Field>
          <Field label="Email *">
            <input
              type="email"
              required
              value={form.email}
              onChange={(e) => update('email', e.target.value)}
              placeholder="name@robonose.lab"
              maxLength={200}
            />
          </Field>
          <Field label="Phòng ban">
            <input value={form.department} onChange={(e) => update('department', e.target.value)} />
          </Field>
          <Field label="Chức danh">
            <input value={form.title} onChange={(e) => update('title', e.target.value)} />
          </Field>
          <Field label="Số điện thoại">
            <input
              type="tel"
              value={form.phone}
              onChange={(e) => update('phone', e.target.value)}
            />
          </Field>
          <Field label="Nhóm">
            <select value={form.group} onChange={(e) => update('group', e.target.value)}>
              <option>Nhóm nghiên cứu</option>
              <option>Nhóm vận hành</option>
            </select>
          </Field>
        </div>
        <p className="field-title">
          Vai trò * <small>Có thể chọn nhiều vai trò</small>
        </p>
        <div className="role-options">
          {roles
            .filter((r) => role === 'Super Admin' || r !== 'Super Admin')
            .map((r) => (
              <label key={r}>
                <input
                  type="checkbox"
                  checked={form.roles.includes(r)}
                  onChange={(e) =>
                    update(
                      'roles',
                      e.target.checked ? [...form.roles, r] : form.roles.filter((v) => v !== r),
                    )
                  }
                />
                {r}
              </label>
            ))}
        </div>
        <Field label="Trạng thái">
          <select value={form.status} onChange={(e) => update('status', e.target.value)}>
            {Object.entries(statusLabel).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="modal-footer">
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit">Lưu người dùng</Button>
        </div>
      </form>
    </Modal>
  );
}
function InviteForm({ onClose }: { onClose: () => void }) {
  const store = useStore();
  const { notify, role } = useApp();
  const [email, setEmail] = useState('');
  const [inviteRole, setRole] = useState<Role>('Viewer');
  const [error, setError] = useState('');
  return (
    <Modal title="Mời thành viên" onClose={onClose}>
      <Notice>Lời mời mô phỏng · không gửi email thật.</Notice>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const clean = email.trim().toLowerCase();
          if (
            store.users.some((u) => u.email === clean) ||
            store.invitations.some((i) => i.email === clean && i.status === 'Pending')
          ) {
            setError('Email đã có tài khoản hoặc lời mời đang chờ.');
            return;
          }
          mockService.update((s) => ({
            ...s,
            invitations: [
              {
                id: crypto.randomUUID(),
                email: clean,
                role: inviteRole,
                status: 'Pending',
                date: new Date().toLocaleDateString('vi-VN'),
              },
              ...s.invitations,
            ],
          }));
          audit(role, 'Mời thành viên demo', clean);
          notify('Đã tạo lời mời mô phỏng.');
          onClose();
        }}
      >
        <Field label="Email">
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Vai trò">
          <select value={inviteRole} onChange={(e) => setRole(e.target.value as Role)}>
            {roles
              .filter((r) => role === 'Super Admin' || r !== 'Super Admin')
              .map((r) => (
                <option key={r}>{r}</option>
              ))}
          </select>
        </Field>
        {error && <p className="form-error">{error}</p>}
        <div className="modal-footer">
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit">Tạo lời mời</Button>
        </div>
      </form>
    </Modal>
  );
}

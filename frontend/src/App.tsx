import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  LayoutDashboard,
  Cpu,
  FlaskConical,
  Layers,
  ContactRound,
  BrainCircuit,
  Boxes,
  Users,
  ShieldCheck,
  LockKeyhole,
  Settings,
  HeartPulse,
  ChartNoAxesCombined,
  UserCircle,
  Search,
  Bell,
  ChevronDown,
  ArrowUpRight,
  LogOut,
  Menu,
  X,
  CircleHelp,
  Command,
  Fingerprint,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { AppContext } from './context';
import { can, roles, roleHome } from './domain';
import type { Module, Role } from './types';
import { useStore, mockService } from './services/store';
import { useDataset } from './services/dataset';
import { Avatar, Badge, Button, Empty, Modal, Notice, SearchBox, Toast } from './components/ui';
import Dashboard from './pages/Dashboard';
import UsersPage from './pages/Users';
import Devices, { Experiments } from './pages/Devices';
import Samples, { People } from './pages/Research';
import { Models } from './pages/AI';
import AI from './pages/Identity';
import { Roles, Security, Settings as SettingsPage, Health, Reports } from './pages/Admin';
import Profile, { Login } from './pages/Profile';
import Tester from './pages/Tester';
type Route = { path: string; label: string; module: Module; icon: LucideIcon; group: string };
const routes: Route[] = [
  {
    path: '/test',
    label: 'Kiểm tra danh tính',
    module: 'testing',
    icon: Fingerprint,
    group: 'WORKSPACE',
  },
  {
    path: '/dashboard',
    label: 'Tổng quan',
    module: 'dashboard',
    icon: LayoutDashboard,
    group: 'WORKSPACE',
  },
  { path: '/devices', label: 'Thiết bị', module: 'devices', icon: Cpu, group: 'WORKSPACE' },
  {
    path: '/experiments',
    label: 'Thu mẫu & thí nghiệm',
    module: 'experiments',
    icon: FlaskConical,
    group: 'WORKSPACE',
  },
  {
    path: '/samples',
    label: 'Thư viện mùi cơ thể',
    module: 'samples',
    icon: Layers,
    group: 'NGHIÊN CỨU',
  },
  {
    path: '/people',
    label: 'Hồ sơ nhận diện',
    module: 'people',
    icon: ContactRound,
    group: 'NGHIÊN CỨU',
  },
  { path: '/ai', label: 'AI & nhận diện', module: 'ai', icon: BrainCircuit, group: 'NGHIÊN CỨU' },
  { path: '/models', label: 'Model Registry', module: 'models', icon: Boxes, group: 'NGHIÊN CỨU' },
  {
    path: '/reports',
    label: 'Báo cáo',
    module: 'reports',
    icon: ChartNoAxesCombined,
    group: 'NGHIÊN CỨU',
  },
  { path: '/users', label: 'Quản lý người dùng', module: 'users', icon: Users, group: 'QUẢN TRỊ' },
  {
    path: '/roles',
    label: 'Vai trò & phân quyền',
    module: 'roles',
    icon: ShieldCheck,
    group: 'QUẢN TRỊ',
  },
  {
    path: '/security',
    label: 'Bảo mật & nhật ký',
    module: 'security',
    icon: LockKeyhole,
    group: 'QUẢN TRỊ',
  },
  {
    path: '/settings',
    label: 'Cài đặt hệ thống',
    module: 'settings',
    icon: Settings,
    group: 'HỆ THỐNG',
  },
  {
    path: '/health',
    label: 'System health',
    module: 'settings',
    icon: HeartPulse,
    group: 'HỆ THỐNG',
  },
  {
    path: '/profile',
    label: 'Tài khoản của tôi',
    module: 'profile',
    icon: UserCircle,
    group: 'HỆ THỐNG',
  },
];
const pages: Record<string, () => React.ReactNode> = {
  '/test': Tester,
  '/dashboard': Dashboard,
  '/users': UsersPage,
  '/devices': Devices,
  '/experiments': Experiments,
  '/samples': Samples,
  '/people': People,
  '/ai': AI,
  '/models': Models,
  '/roles': Roles,
  '/security': Security,
  '/settings': SettingsPage,
  '/health': Health,
  '/reports': Reports,
  '/profile': Profile,
};
function readRole(): Role {
  try {
    const saved = sessionStorage.getItem('robonose.demo-role');
    return roles.includes(saved as Role) ? (saved as Role) : 'Tester';
  } catch {
    return 'Tester';
  }
}
export default function App() {
  const s = useStore();
  const dataset = useDataset();
  const [role, setRole] = useState<Role>(readRole);
  const [logged, setLogged] = useState(() => {
    try {
      return sessionStorage.getItem('robonose.demo-session') !== 'out';
    } catch {
      return true;
    }
  });
  const [path, setPath] = useState(location.hash.slice(1).split('?')[0] || roleHome(role));
  const [routeRevision, setRouteRevision] = useState(0);
  const [toast, setToast] = useState('');
  const [mobile, setMobile] = useState(false);
  const [search, setSearch] = useState(false);
  const [query, setQuery] = useState('');
  const [notifications, setNotifications] = useState(false);
  const [help, setHelp] = useState(false);
  const [roleMenu, setRoleMenu] = useState(false);
  const notify = useCallback((message: string) => setToast(message), []);
  const closeToast = useCallback(() => setToast(''), []);
  const allowed = useCallback(
    (module: Module, action: Parameters<typeof can>[3] = 'view') =>
      can(s.permissions, role, module, action),
    [s.permissions, role],
  );
  useEffect(() => {
    const handle = () => {
      setPath(location.hash.slice(1).split('?')[0] || roleHome(readRole()));
      setRouteRevision((v) => v + 1);
      setMobile(false);
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', handle);
    return () => window.removeEventListener('hashchange', handle);
  }, []);
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setSearch((v) => !v);
      }
      if (e.key === 'Escape') {
        setMobile(false);
        setRoleMenu(false);
      }
    }
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, []);
  const active = routes.find((r) => r.path === path);
  const Page = pages[path];
  const currentUser = s.users.find((u) => u.roles.includes(role)) ?? s.users[0];
  function switchRole(r: Role) {
    setRole(r);
    setRoleMenu(false);
    try {
      sessionStorage.setItem('robonose.demo-role', r);
    } catch {}
    if (r === 'Tester' || (active && !can(s.permissions, r, active.module)))
      location.hash = roleHome(r);
  }
  function login(r: Role) {
    switchRole(r);
    setLogged(true);
    try {
      sessionStorage.setItem('robonose.demo-session', 'in');
    } catch {}
    location.hash = roleHome(r);
  }
  return (
    <AppContext.Provider value={{ role, notify, allowed }}>
      {!logged ? (
        <Login onLogin={login} />
      ) : (
        <div className="app-shell">
          {mobile && (
            <button
              className="sidebar-overlay"
              aria-label="Đóng menu"
              onClick={() => setMobile(false)}
            />
          )}
          <aside className={`sidebar ${mobile ? 'mobile-open' : ''}`}>
            <a className="brand" href={'#' + roleHome(role)}>
              <span className="brand-icon">
                <Activity size={25} />
              </span>
              <span>
                robonose<span className="brand-label">BIOID WORKSPACE</span>
              </span>
            </a>
            <div className="workspace-switch">
              <span className="workspace-mark">R</span>
              <div>
                <strong>{role === 'Tester' ? 'Identity Check' : 'Research Lab'}</strong>
                <small>
                  {role === 'Tester' ? 'Ứng dụng kiểm tra mùi' : 'Không gian nghiên cứu'}
                </small>
              </div>
              <Badge tone="purple">DEMO</Badge>
            </div>
            <nav aria-label="Điều hướng chính">
              {['WORKSPACE', 'NGHIÊN CỨU', 'QUẢN TRỊ', 'HỆ THỐNG'].map((group) => {
                const items = routes.filter((r) => r.group === group && allowed(r.module));
                return items.length ? (
                  <div className="nav-group" key={group}>
                    <span className="nav-label">{group}</span>
                    {items.map((r) => (
                      <a
                        key={r.path}
                        href={'#' + r.path}
                        aria-current={path === r.path ? 'page' : undefined}
                        className={path === r.path ? 'active' : ''}
                      >
                        <r.icon size={18} />
                        <span>{r.label}</span>
                        {r.path === '/samples' && <small>{dataset.catalog.samples.length}</small>}
                      </a>
                    ))}
                  </div>
                ) : null;
              })}
            </nav>
            <div className="sidebar-bottom">
              <div className="demo-note">
                <span>
                  <span className="live-dot" />
                  CHẾ ĐỘ XEM TRƯỚC
                </span>
                <p>
                  UI demo · data gốc chỉ đọc.
                  <br />
                  Sẵn sàng cho bước tích hợp.
                </p>
                <button onClick={() => setHelp(true)}>
                  Thông tin bản demo <ArrowUpRight size={13} />
                </button>
              </div>
              <button className="sidebar-account" onClick={() => (location.hash = '/profile')}>
                <Avatar name={currentUser?.name ?? role} small />
                <div>
                  <strong>{currentUser?.name ?? role}</strong>
                  <small>{role}</small>
                </div>
              </button>
              <button
                className="logout-button"
                onClick={() => {
                  setLogged(false);
                  try {
                    sessionStorage.setItem('robonose.demo-session', 'out');
                  } catch {}
                }}
              >
                <LogOut size={15} />
                Đăng xuất demo
              </button>
            </div>
          </aside>
          <div className="main-area">
            <header className="topbar">
              <div className="breadcrumb">
                <button
                  className="icon-button mobile-menu"
                  aria-label="Mở điều hướng"
                  onClick={() => setMobile(true)}
                >
                  <Menu size={21} />
                </button>
                <span>Workspace</span>
                <span>/</span>
                <strong>{active?.label ?? 'Không tìm thấy'}</strong>
              </div>
              <div className="topbar-actions">
                <button className="global-search" onClick={() => setSearch(true)}>
                  <Search size={16} />
                  <span>Tìm nhanh…</span>
                  <kbd>Ctrl K</kbd>
                </button>
                <div className="role-switch">
                  <button onClick={() => setRoleMenu((v) => !v)} aria-expanded={roleMenu}>
                    <span className="role-dot" />
                    {role}
                    <ChevronDown size={13} />
                  </button>
                  {roleMenu && (
                    <>
                      <button
                        className="menu-dismiss"
                        aria-label="Đóng chọn vai trò"
                        onClick={() => setRoleMenu(false)}
                      />
                      <div className="role-dropdown">
                        <small>XEM TRƯỚC THEO VAI TRÒ</small>
                        {roles.map((r) => (
                          <button
                            key={r}
                            className={r === role ? 'active' : ''}
                            onClick={() => switchRole(r)}
                          >
                            {r}
                            {r === role && <ShieldCheck size={14} />}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
                <button
                  className="icon-button notification-button"
                  aria-label="Thông báo"
                  onClick={() => setNotifications(true)}
                >
                  <Bell size={19} />
                  <i />
                </button>
                <button
                  className="icon-button"
                  aria-label="Hướng dẫn"
                  onClick={() => setHelp(true)}
                >
                  <CircleHelp size={19} />
                </button>
                <button
                  className="profile-top"
                  aria-label="Mở hồ sơ cá nhân"
                  onClick={() => (location.hash = '/profile')}
                >
                  <Avatar name={currentUser?.name ?? role} small />
                </button>
              </div>
            </header>
            <main key={role + path + routeRevision}>
              {mockService.warning() && <Notice tone="amber">{mockService.warning()}</Notice>}
              {!Page ? (
                <Empty
                  title="Không tìm thấy màn hình"
                  description="Chọn một mục trong sidebar để tiếp tục."
                />
              ) : active && !allowed(active.module) ? (
                <div className="forbidden">
                  <LockKeyhole size={40} />
                  <h1>403 · Không có quyền truy cập</h1>
                  <p>Vai trò {role} chưa được cấp quyền xem màn hình này.</p>
                  <Button onClick={() => (location.hash = '/dashboard')}>Về tổng quan</Button>
                </div>
              ) : (
                <Page />
              )}
              <footer className="app-footer">
                <span>
                  RoboNose BioID <i /> Research workspace
                </span>
                <span>Frontend preview · v0.1.0</span>
              </footer>
            </main>
          </div>
        </div>
      )}
      {toast && <Toast message={toast} onClose={closeToast} />}{' '}
      {search && (
        <Modal title="Tìm nhanh trong workspace" onClose={() => setSearch(false)}>
          <SearchBox value={query} onChange={setQuery} placeholder="Tên màn hình, chức năng…" />
          <div className="search-results">
            {routes
              .filter(
                (r) => allowed(r.module) && r.label.toLowerCase().includes(query.toLowerCase()),
              )
              .map((r) => (
                <button
                  key={r.path}
                  onClick={() => {
                    location.hash = r.path;
                    setSearch(false);
                    setQuery('');
                  }}
                >
                  <r.icon size={17} />
                  {r.label}
                  <ArrowUpRight size={14} />
                </button>
              ))}
          </div>
        </Modal>
      )}
      {notifications && (
        <Modal title="Thông báo & cảnh báo" onClose={() => setNotifications(false)}>
          <Notice>Thông báo minh họa, chưa có nguồn sự kiện realtime.</Notice>
          <div className="notification-item">
            <Badge tone="amber">MODEL</Badge>
            <div>
              <strong>Kiểm tra schema trước khi nhận diện</strong>
              <p>Model legacy và bộ cảm biến S3 có cấu hình đầu vào khác nhau.</p>
            </div>
          </div>
          <div className="notification-item">
            <Badge tone="purple">DEMO</Badge>
            <div>
              <strong>Workspace đang chạy cục bộ</strong>
              <p>Thay đổi dữ liệu được lưu trên trình duyệt này.</p>
            </div>
          </div>
          <div className="notification-item">
            <Badge tone="green">USER</Badge>
            <div>
              <strong>
                {s.invitations.filter((i) => i.status === 'Pending').length} lời mời đang chờ
              </strong>
              <p>Xem tại Quản lý người dùng → Lời mời.</p>
            </div>
          </div>
        </Modal>
      )}
      {help && (
        <Modal title="RoboNose · Frontend preview" onClose={() => setHelp(false)}>
          <p>Không gian giao diện cho nghiên cứu nhận diện người bằng mùi cơ thể.</p>
          <ul className="help-list">
            <li>Chuyển vai trò ở topbar để xem sidebar và quyền thao tác.</li>
            <li>
              User, hồ sơ và cấu hình UI lưu trong localStorage. Mẫu thật đọc trực tiếp data/ và
              không cho sửa/xóa.
            </li>
            <li>Thu mẫu và AI chỉ mô phỏng; không kết nối Serial hoặc chạy model.</li>
            <li>Tìm nhanh bằng Ctrl K. Nhấn Escape để đóng hộp thoại.</li>
            <li>Đọc frontend/README.md để chạy và tích hợp backend.</li>
          </ul>
        </Modal>
      )}
    </AppContext.Provider>
  );
}

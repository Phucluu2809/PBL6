import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  ArrowDownToLine,
  ArrowUpRight,
  ChevronDown,
  Search,
  X,
  Check,
  Inbox,
  AlertTriangle,
} from 'lucide-react';
export function Button({
  children,
  onClick,
  variant = 'primary',
  disabled = false,
  type = 'button',
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: string;
  disabled?: boolean;
  type?: 'button' | 'submit';
}) {
  return (
    <button type={type} className={`button ${variant}`} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return (
    <span className={`badge ${tone}`}>
      <i />
      {children}
    </span>
  );
}
export const statusTone = (status: string) =>
  ['Active', 'PASS', 'Connected', 'Accepted', 'Hoàn thành'].includes(status)
    ? 'green'
    : ['Locked', 'FAIL', 'Error', 'Revoked', 'Disabled'].includes(status)
      ? 'red'
      : ['Pending', 'REVIEW', 'Expired'].includes(status)
        ? 'amber'
        : 'purple';
export function Stat({
  label,
  value,
  detail,
  icon,
  tone = 'purple',
}: {
  label: string;
  value: ReactNode;
  detail: string;
  icon: ReactNode;
  tone?: string;
}) {
  return (
    <div className="stat">
      <div className="stat-top">
        <span>{label}</span>
        <span className={`stat-icon ${tone}`}>{icon}</span>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
export function PageTitle({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="title-actions">{actions}</div>
    </div>
  );
}
export function Panel({
  title,
  description,
  actions,
  children,
  className = '',
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-heading">
          <div>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}
export function Tabs({
  items,
  value,
  onChange,
}: {
  items: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map((t) => (
        <button
          key={t}
          role="tab"
          aria-selected={value === t}
          className={value === t ? 'active' : ''}
          onClick={() => onChange(t)}
        >
          {t}
        </button>
      ))}
    </div>
  );
}
export function SearchBox({
  value,
  onChange,
  placeholder = 'Tìm kiếm…',
}: {
  value: string;
  onChange: (s: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="search-box">
      <Search size={17} />
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button aria-label="Xóa tìm kiếm" onClick={() => onChange('')}>
          <X size={14} />
        </button>
      )}
    </label>
  );
}
export function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (s: string) => void;
  options: string[];
}) {
  return (
    <label className="select-wrap">
      <span className="sr-only">{label}</span>
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
      <ChevronDown size={14} />
    </label>
  );
}
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function Avatar({ name, small = false }: { name: string; small?: boolean }) {
  const initials = name
    .trim()
    .split(/\s+/)
    .slice(-2)
    .map((s) => s[0])
    .join('');
  const hue = name.length % 4;
  return <span className={`avatar avatar-${hue} ${small ? 'small' : ''}`}>{initials}</span>;
}
export function Empty({
  title = 'Không có dữ liệu',
  description = 'Thử thay đổi bộ lọc hoặc tạo bản ghi mới.',
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="empty">
      <Inbox size={32} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
export function Notice({ children, tone = 'purple' }: { children: ReactNode; tone?: string }) {
  return (
    <div className={`notice ${tone}`}>
      <AlertTriangle size={17} />
      <span>{children}</span>
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const bodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const root = ref.current;
    root?.querySelector<HTMLElement>('input,button,select,textarea')?.focus();
    function key(e: KeyboardEvent) {
      if (e.key === 'Escape') close.current();
      if (e.key === 'Tab' && root) {
        const nodes = Array.from(
          root.querySelectorAll<HTMLElement>(
            'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]',
          ),
        );
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener('keydown', key);
    return () => {
      document.body.style.overflow = bodyOverflow;
      document.removeEventListener('keydown', key);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`modal ${wide ? 'wide' : ''}`}
      >
        <div className="modal-heading">
          <h2>{title}</h2>
          <button className="icon-button" aria-label="Đóng" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
export function Confirm({
  title,
  description,
  onConfirm,
  onClose,
}: {
  title: string;
  description: string;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal title={title} onClose={onClose}>
      <p className="muted">{description}</p>
      <div className="modal-footer">
        <Button variant="secondary" onClick={onClose}>
          Hủy
        </Button>
        <Button
          variant="danger"
          onClick={() => {
            onConfirm();
            onClose();
          }}
        >
          Xác nhận
        </Button>
      </div>
    </Modal>
  );
}
export function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4500);
    return () => clearTimeout(t);
  }, [message, onClose]);
  return (
    <div className="toast" role="status">
      <Check size={18} />
      {message}
      <button aria-label="Đóng thông báo" onClick={onClose}>
        <X size={15} />
      </button>
    </div>
  );
}
export function Chart({ compact = false, seed = 0 }: { compact?: boolean; seed?: number }) {
  const [channel, setChannel] = useState(0);
  const colors = ['#8768d7', '#51aaa3', '#e8b05d'];
  const paths = colors.map((_, c) =>
    Array.from({ length: 100 }, (_, i) => {
      const bump = Math.exp(-Math.pow((i - 48) / 20, 2)) * (70 + c * 12);
      const v = 135 - bump + Math.sin(i * 0.7 + c + seed) * 5 + Math.cos(i * 0.29 + c) * 4 + c * 11;
      return `${i === 0 ? 'M' : 'L'}${i * 6.5},${v}`;
    }).join(' '),
  );
  return (
    <div className={`chart ${compact ? 'compact' : ''}`}>
      {!compact && (
        <div className="chart-legend">
          {['TGS2602', 'MQ3 #1', 'BME688 gas'].map((n, i) => (
            <button
              key={n}
              onClick={() => setChannel(i)}
              className={channel === i ? 'selected' : ''}
            >
              <i style={{ background: colors[i] }} />
              {n}
            </button>
          ))}
          <span>Tín hiệu chuẩn hóa · mô phỏng</span>
        </div>
      )}
      <svg viewBox="0 0 700 210" role="img" aria-label="Biểu đồ tín hiệu mô phỏng theo thời gian">
        <defs>
          <linearGradient id={`chart-fill-${seed}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colors[channel]} stopOpacity=".15" />
            <stop offset="100%" stopColor={colors[channel]} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[35, 75, 115, 155].map((y, i) => (
          <g key={y}>
            <line x1="34" y1={y} x2="680" y2={y} stroke="#eeedf3" strokeDasharray="4 4" />
            <text x="3" y={y + 4}>
              {(1 - i * 0.25).toFixed(2)}
            </text>
          </g>
        ))}
        <rect x="197" y="20" width="320" height="155" fill="#f5f2fc" />
        <text x="310" y="34" fill="#9476c4">
          EXPOSURE
        </text>
        <g transform="translate(34, 0)">
          <path d={`${paths[channel]} L643,175 L0,175 Z`} fill={`url(#chart-fill-${seed})`} />
          {paths.map((p, i) => (
            <path
              key={i}
              d={p}
              stroke={colors[i]}
              strokeWidth={i === channel ? 2.6 : 1.5}
              opacity={i === channel ? 1 : 0.5}
              fill="none"
            />
          ))}
        </g>
        {['0s', '60s', '120s', '180s', '240s'].map((n, i) => (
          <text key={n} x={34 + i * 157} y="202">
            {n}
          </text>
        ))}
      </svg>
    </div>
  );
}
export function DownloadButton({ onClick }: { onClick: () => void }) {
  return (
    <Button variant="secondary" onClick={onClick}>
      <ArrowDownToLine size={15} />
      Xuất dữ liệu
    </Button>
  );
}
export function TextLink({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button className="text-link" onClick={onClick}>
      {children}
      <ArrowUpRight size={14} />
    </button>
  );
}

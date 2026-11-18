import {
  Fingerprint,
  ArrowRight,
  FolderOpen,
  Plus,
  ShieldCheck,
  Users,
  RefreshCw,
} from 'lucide-react';
import { useStore } from '../services/store';
import { useDataset, refreshDataset, personName } from '../services/dataset';
import { useApp } from '../context';
import DatasetCharts from '../components/DatasetCharts';
import {
  Avatar,
  Badge,
  Button,
  Empty,
  PageTitle,
  Panel,
  Stat,
  TextLink,
  Notice,
} from '../components/ui';
export default function Dashboard() {
  const s = useStore();
  const { catalog, loading, error } = useDataset();
  const { allowed } = useApp();
  const latest = catalog.samples.find((v) => (v.rowCount ?? 0) > 0 && v.person !== 'UNASSIGNED');
  return (
    <>
      <PageTitle
        eyebrow="ROBONOSE / BODY ODOR IDENTITY"
        title="Nhận diện qua dấu ấn mùi cơ thể"
        description="Hồ sơ danh tính, mẫu tham chiếu và tín hiệu thật trong cùng một không gian."
        actions={
          <>
            {allowed('testing') && (
              <Button onClick={() => (location.hash = '/test')}>
                <Fingerprint size={16} />
                Mở ứng dụng kiểm tra
              </Button>
            )}
            <Button variant="secondary" disabled={loading} onClick={() => void refreshDataset()}>
              <RefreshCw size={15} />
              Đọc lại data/
            </Button>
            {allowed('experiments', 'control') && (
              <Button onClick={() => (location.hash = '/experiments')}>
                <Plus size={15} />
                Thu mẫu mới
              </Button>
            )}
          </>
        }
      />
      <div className="welcome-banner">
        <div>
          <span className="eyebrow">A DIFFERENT WAY TO RECOGNIZE</span>
          <h2>Một người. Một dấu ấn mùi.</h2>
          <p>Thu trực tiếp mùi cơ thể → lưu mẫu tham chiếu → đối chiếu và nhận diện danh tính.</p>
          <button onClick={() => (location.hash = '/people')}>
            Khám phá hồ sơ nhận diện <ArrowRight size={16} />
          </button>
        </div>
        <div className="signal-art" aria-hidden="true">
          <div className="orbit one" />
          <div className="orbit two" />
          <Fingerprint size={80} strokeWidth={1} />
        </div>
      </div>
      {error && <Notice tone="amber">{error}</Notice>}
      <div className="stats-grid">
        <Stat
          label="Danh tính trong hệ thống"
          value="03"
          detail="Nguyễn Văn Tài · Nguyễn Văn Dương · Lưu Hoàng Phúc"
          icon={<Fingerprint size={19} />}
        />
        <Stat
          label="Lượt thu gốc"
          value={loading ? '…' : catalog.samples.length}
          detail="Đọc trực tiếp từ data/, không sao chép"
          icon={<FolderOpen size={19} />}
          tone="blue"
        />
        <Stat
          label="Đã ghép hồ sơ theo nhãn"
          value={catalog.samples.filter((v) => v.person !== 'UNASSIGNED').length}
          detail="Giữ nguyên nhãn gốc trong metadata"
          icon={<Users size={19} />}
          tone="green"
        />
        <Stat
          label="Bảo toàn dữ liệu"
          value="Chỉ đọc"
          detail="Không sửa hoặc xóa file dữ liệu gốc"
          icon={<ShieldCheck size={19} />}
          tone="amber"
        />
      </div>
      <div className="identity-grid">
        {s.people.map((p) => {
          const rows = catalog.samples.filter((v) => v.person === p.id);
          return (
            <button
              className="identity-shortcut"
              key={p.id}
              onClick={() => (location.hash = `/samples?person=${p.id}`)}
            >
              <Avatar name={p.name} />
              <div>
                <strong>{p.name}</strong>
                <small>{rows.length} lượt thu · mùi cơ thể</small>
              </div>
              <ArrowRight size={16} />
            </button>
          );
        })}
      </div>
      <div className="dashboard-columns">
        <Panel
          title="Tín hiệu lượt thu gần đây"
          description={
            latest
              ? `${latest.name} · ${personName(latest.person)}`
              : 'Đang tìm lượt thu có tín hiệu'
          }
          actions={
            latest && (
              <TextLink onClick={() => (location.hash = `/samples?id=${latest.id}`)}>
                Mở mẫu
              </TextLink>
            )
          }
        >
          {latest ? (
            <DatasetCharts id={latest.id} compact />
          ) : loading ? (
            <div className="empty">
              <div className="spinner" />
              <p>Đang đọc thư mục data/…</p>
            </div>
          ) : (
            <Empty
              title="Chưa có mẫu phù hợp"
              description="Mở Thư viện mùi cơ thể để xem toàn bộ lượt thu và mẫu đối chứng."
            />
          )}
        </Panel>
        <Panel
          title="Luồng nhận diện"
          description="Cùng cách tổ chức như hệ thống nhận diện khuôn mặt"
        >
          <div className="identity-flow">
            {[
              ['01', 'Hồ sơ người', 'Ba danh tính với các mẫu mùi tham chiếu.'],
              [
                '02',
                'Thu trực tiếp mùi cơ thể',
                'Ghi tín hiệu cảm biến theo protocol, không chọn vị trí.',
              ],
              [
                '03',
                'Đối chiếu danh tính',
                'Hiển thị điểm tương đồng, ngưỡng và Unknown sau khi tích hợp model.',
              ],
            ].map(([n, title, desc]) => (
              <div key={n}>
                <span>{n}</span>
                <div>
                  <strong>{title}</strong>
                  <p>{desc}</p>
                </div>
              </div>
            ))}
          </div>
          <Notice>
            Dữ liệu và biểu đồ là thật. Luồng chạy AI mới vẫn là mô phỏng; kết quả có sẵn trong
            prediction.json được xem nguyên bản.
          </Notice>
        </Panel>
      </div>
      <Panel
        title="Lượt thu gần đây"
        description="Mẫu gốc và đối chứng được giữ nhãn riêng"
        actions={<TextLink onClick={() => (location.hash = '/samples')}>Xem thư viện</TextLink>}
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Nhãn gốc</th>
                <th>Hồ sơ</th>
                <th>Ngày thu</th>
                <th>Kết luận QC gốc</th>
                <th>Dữ liệu</th>
              </tr>
            </thead>
            <tbody>
              {catalog.samples.slice(0, 6).map((v) => (
                <tr key={v.id}>
                  <td>
                    <button
                      className="text-link"
                      onClick={() => (location.hash = `/samples?id=${v.id}`)}
                    >
                      {v.name} ↗
                    </button>
                  </td>
                  <td>{personName(v.person)}</td>
                  <td>
                    {v.date
                      ? new Date(v.date).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })
                      : '—'}
                  </td>
                  <td>
                    <Badge tone="neutral">{v.qcSource}</Badge>
                  </td>
                  <td>{v.rowCount} dòng</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

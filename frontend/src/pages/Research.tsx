import { useEffect, useState } from 'react';
import {
  Fingerprint,
  FolderOpen,
  LockKeyhole,
  RefreshCw,
  Scale,
  FileJson,
  Layers,
  CheckCheck,
  Users,
} from 'lucide-react';
import { useApp } from '../context';
import { useStore, mockService, download, audit } from '../services/store';
import { useDataset, refreshDataset, invalidateDetailCache, personName } from '../services/dataset';
import type { Sample, Person } from '../types';
import { csvCell } from '../domain';
import DatasetCharts, { SampleEvidence } from '../components/DatasetCharts';
import {
  Avatar,
  Badge,
  Button,
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
  statusTone,
} from '../components/ui';

export function SampleViewer({ sample, onClose }: { sample: Sample; onClose: () => void }) {
  const [tab, setTab] = useState('Biểu đồ tín hiệu');
  return (
    <Modal title={sample.name ?? sample.id} wide onClose={onClose}>
      <div className="sample-view-heading">
        <div>
          <strong>{personName(sample.person)}</strong>
          <p>{sample.sourcePath ?? 'Metadata phiên demo · chưa có raw.csv'}</p>
        </div>
        <Badge tone="green">
          <LockKeyhole size={11} />
          Chỉ đọc
        </Badge>
      </div>
      <Tabs
        items={['Biểu đồ tín hiệu', 'Thông tin', 'QC & metadata', 'File & pha đo', 'Nhận diện']}
        value={tab}
        onChange={setTab}
      />
      {tab === 'Thông tin' ? (
        <dl className="detail-grid">
          {Object.entries({
            'Nhãn gốc': sample.name ?? sample.id,
            'Hồ sơ ghép theo nhãn': personName(sample.person),
            'Phương thức': 'Thu trực tiếp mùi cơ thể — không phân vị trí',
            'Trạng thái quy trình': sample.processStatus ?? 'Demo',
            'QC gốc': sample.qcSource ?? 'Chưa đánh giá',
            Schema: sample.schema ?? 'Demo',
            Protocol: sample.protocol,
            'Thời lượng toàn file': `${sample.duration.toFixed(1)}s`,
            'Ngày thu': sample.date || 'Không có timestamp',
            Nguồn: sample.sourcePath ?? 'Phiên demo',
          }).map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      ) : sample.readOnly ? (
        tab === 'Biểu đồ tín hiệu' ? (
          <DatasetCharts id={sample.id} />
        ) : (
          <SampleEvidence id={sample.id} tab={tab} />
        )
      ) : (
        <Empty
          title="Phiên demo chưa có dữ liệu gốc"
          description="Metadata chỉ lưu trên trình duyệt. Không sinh hoặc ghi raw.csv vào thư mục data/."
        />
      )}
    </Modal>
  );
}
export default function Samples() {
  const store = useStore();
  const { allowed, notify } = useApp();
  const { catalog, loading, error } = useDataset();
  const [query, setQuery] = useState('');
  const [qc, setQc] = useState('Tất cả QC');
  const [person, setPerson] = useState('Tất cả hồ sơ');
  const [date, setDate] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [view, setView] = useState<Sample | null>(null);
  const [comparison, setComparison] = useState(false);
  const [page, setPage] = useState(1);
  const all = [...catalog.samples, ...store.samples.filter((v) => !v.readOnly)];
  useEffect(() => {
    const params = new URLSearchParams(location.hash.split('?')[1]);
    const id = params.get('id');
    const person = params.get('person');
    if (id) {
      const found = catalog.samples.find((v) => v.id === id);
      if (found) setView(found);
    }
    if (person) setPerson(person);
  }, [catalog]);
  const filtered = all.filter(
    (v) =>
      [v.name, v.id, v.person, personName(v.person), v.sourcePath]
        .join(' ')
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (qc === 'Tất cả QC' || v.qc === qc) &&
      (person === 'Tất cả hồ sơ' || person === v.person) &&
      (!date || v.date.startsWith(date)),
  );
  const current = Math.min(page, Math.max(1, Math.ceil(filtered.length / 12)));
  const rows = filtered.slice((current - 1) * 12, current * 12);
  function toggle(id: string) {
    if (!selected.includes(id) && selected.length === 5) {
      notify('Chọn tối đa 5 mẫu.');
      return;
    }
    setSelected((v) => (v.includes(id) ? v.filter((x) => x !== id) : [...v, id]));
  }
  return (
    <>
      <PageTitle
        eyebrow="BODY ODOR IDENTITY / DỮ LIỆU GỐC"
        title="Thư viện mùi cơ thể"
        description="Mở một lượt thu để xem tín hiệu cảm biến thật và hồ sơ nhận diện liên quan."
        actions={
          <>
            <Button
              variant="secondary"
              disabled={loading}
              onClick={() => {
                invalidateDetailCache();
                void refreshDataset();
              }}
            >
              <RefreshCw size={15} />
              Đọc lại data/
            </Button>
            <Button
              variant="secondary"
              disabled={selected.length < 2}
              onClick={() => setComparison(true)}
            >
              <Scale size={15} />
              So sánh ({selected.length}/5)
            </Button>
          </>
        }
      />
      <Notice>
        Liên kết trực tiếp thư mục data/ · Chỉ đọc. Không có chức năng sửa, xóa hoặc ghi QC lên mẫu
        gốc. Nhãn chưa xác định và mẫu đối chứng được giữ riêng, không tự nhận là một trong ba
        người.
      </Notice>
      {error && (
        <Notice tone="amber">
          {error}{' '}
          <Button variant="ghost" onClick={() => void refreshDataset()}>
            Thử lại
          </Button>
        </Notice>
      )}
      {catalog.warnings.length > 0 && (
        <Notice tone="amber">
          {catalog.warnings.length} file có vấn đề khi đọc.{' '}
          <details>
            <summary>Xem chi tiết</summary>
            {catalog.warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
          </details>
        </Notice>
      )}
      <div className="stats-grid">
        <Stat
          label="Lượt thu trong data/"
          value={loading ? '…' : catalog.samples.length}
          detail={`${catalog.skippedSessions} log phiên tổng không đếm trùng`}
          icon={<FolderOpen size={19} />}
        />
        <Stat
          label="Hồ sơ nhận diện"
          value="03"
          detail="Tài · Dương · Phúc"
          icon={<Fingerprint size={19} />}
          tone="blue"
        />
        <Stat
          label="Lượt đã ghép nhãn"
          value={catalog.samples.filter((v) => v.person !== 'UNASSIGNED').length}
          detail="Ghép nhãn gốc, chưa phải kết quả AI"
          icon={<Users size={19} />}
          tone="green"
        />
        <Stat
          label="Cần kiểm tra QC"
          value={catalog.samples.filter((v) => v.qc === 'REVIEW').length}
          detail="Giữ kết luận gốc, không suy PASS"
          icon={<CheckCheck size={19} />}
          tone="amber"
        />
      </div>
      <Panel
        title="Các lượt thu"
        description="Bấm tên mẫu hoặc Xem biểu đồ để mở dữ liệu gốc"
        actions={
          allowed('samples', 'export') && (
            <Button
              variant="secondary"
              onClick={() => download('robonose-catalog.json', JSON.stringify(filtered, null, 2))}
            >
              <FileJson size={15} />
              Xuất danh mục
            </Button>
          )
        }
      >
        <div className="table-toolbar">
          <SearchBox
            value={query}
            onChange={(v) => {
              setQuery(v);
              setPage(1);
            }}
            placeholder="Tìm nhãn mẫu, người hoặc đường dẫn…"
          />
          <div className="filters">
            <Select
              label="QC"
              value={qc}
              onChange={(v) => {
                setQc(v);
                setPage(1);
              }}
              options={['Tất cả QC', 'PASS', 'REVIEW', 'FAIL']}
            />
            <label className="select-wrap">
              <select
                aria-label="Hồ sơ nhận diện"
                value={person}
                onChange={(e) => {
                  setPerson(e.target.value);
                  setPage(1);
                }}
              >
                <option>Tất cả hồ sơ</option>
                {store.people.map((p) => (
                  <option value={p.id} key={p.id}>
                    {p.name}
                  </option>
                ))}
                <option value="UNASSIGNED">Mẫu khác / đối chứng</option>
              </select>
            </label>
            <input
              type="date"
              aria-label="Ngày thu"
              value={date}
              onChange={(e) => {
                setDate(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
        {loading ? (
          <div className="empty" role="status">
            <div className="spinner" />
            <h3>Đang lập danh mục data/</h3>
            <p>Đọc metadata và raw.csv, không thay đổi file gốc.</p>
          </div>
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Chọn</th>
                    <th>Nhãn mẫu / nguồn</th>
                    <th>Hồ sơ</th>
                    <th>Ngày thu</th>
                    <th>Dữ liệu</th>
                    <th>Chất lượng</th>
                    <th>Mở mẫu</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((v) => (
                    <tr key={v.id}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Chọn ${v.name ?? v.id}`}
                          checked={selected.includes(v.id)}
                          disabled={!v.readOnly}
                          onChange={() => toggle(v.id)}
                        />
                      </td>
                      <td>
                        <button className="sample-label" onClick={() => setView(v)}>
                          <strong>{v.name ?? v.id}</strong>
                          <small>
                            {v.sourcePath?.split('/').slice(0, -1).join('/') ??
                              'Phiên demo trong trình duyệt'}
                          </small>
                        </button>
                      </td>
                      <td>{personName(v.person)}</td>
                      <td className="nowrap">
                        {v.date
                          ? new Date(v.date).toLocaleString('vi-VN', {
                              timeZone: 'Asia/Ho_Chi_Minh',
                            })
                          : 'Không có timestamp'}
                      </td>
                      <td>
                        {v.rowCount ?? '—'} dòng
                        <small className="cell-sub">
                          {v.duration.toFixed(1)}s · {v.device}
                        </small>
                      </td>
                      <td>
                        <Badge tone={statusTone(v.qc)}>{v.qc}</Badge>
                        <small className="cell-sub">{v.qcSource ?? 'Metadata demo'}</small>
                      </td>
                      <td>
                        <Button variant="ghost" onClick={() => setView(v)}>
                          Xem biểu đồ ↗
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!rows.length && (
              <Empty
                title={error ? 'Chưa tải được dữ liệu' : 'Không có lượt thu phù hợp'}
                description="Đọc lại data/ hoặc thay đổi bộ lọc."
              />
            )}
            <div className="pagination">
              <span>
                {filtered.length} lượt · trang {current}/
                {Math.max(1, Math.ceil(filtered.length / 12))}
              </span>
              <div>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setQuery('');
                    setQc('Tất cả QC');
                    setPerson('Tất cả hồ sơ');
                    setDate('');
                    setPage(1);
                  }}
                >
                  Xóa bộ lọc
                </Button>
                <Button
                  variant="secondary"
                  disabled={current === 1}
                  onClick={() => setPage(current - 1)}
                >
                  Trước
                </Button>
                <Button
                  variant="secondary"
                  disabled={current * 12 >= filtered.length}
                  onClick={() => setPage(current + 1)}
                >
                  Tiếp
                </Button>
              </div>
            </div>
          </>
        )}
      </Panel>
      {view && <SampleViewer sample={view} onClose={() => setView(null)} />}
      {comparison && (
        <Modal title="Đối chiếu tín hiệu các lượt thu" wide onClose={() => setComparison(false)}>
          <Notice>
            Mỗi biểu đồ giữ đơn vị và trục riêng theo raw.csv. Không trộn schema, không nội suy hoặc
            đồng nhất cảm biến khác loại.
          </Notice>
          <div className="compare-grid">
            {catalog.samples
              .filter((v) => selected.includes(v.id))
              .map((v) => (
                <Panel title={v.name} description={personName(v.person)} key={v.id}>
                  <DatasetCharts id={v.id} compact />
                </Panel>
              ))}
          </div>
        </Modal>
      )}
    </>
  );
}
export function People() {
  const s = useStore();
  const { catalog, loading, error } = useDataset();
  const { allowed, notify, role } = useApp();
  const [history, setHistory] = useState<string | null>(null);
  const [editing, setEditing] = useState<Person | null>(null);
  const [view, setView] = useState<Sample | null>(null);
  return (
    <>
      <PageTitle
        eyebrow="BODY ODOR IDENTITY / DANH TÍNH"
        title="Hồ sơ nhận diện"
        description="Mỗi người có một hồ sơ mùi cơ thể và các lượt thu tham chiếu, tương tự hồ sơ khuôn mặt."
      />
      <Notice>
        Thu trực tiếp mùi cơ thể, không chia vị trí. Ghép nhãn trong thư viện chỉ giúp tổ chức dữ
        liệu; nhận diện thật cần model được tích hợp và đánh giá.
      </Notice>
      {error && <Notice tone="amber">{error}</Notice>}
      <div className="identity-grid">
        {s.people.map((p) => {
          const samples = catalog.samples.filter((v) => v.person === p.id);
          return (
            <Panel key={p.id}>
              <div className="identity-card">
                <Avatar name={p.name} />
                <Badge tone="purple">
                  <Fingerprint size={12} />
                  {p.id}
                </Badge>
                <h2>{p.name}</h2>
                <p>Mùi cơ thể · hồ sơ tham chiếu</p>
                <div className="identity-stats">
                  <strong>
                    {loading ? '…' : samples.length}
                    <small>Lượt thu gốc</small>
                  </strong>
                  <strong>
                    {new Set(samples.map((v) => v.date.slice(0, 10))).size}
                    <small>Ngày lấy mẫu</small>
                  </strong>
                </div>
                <Badge tone={p.consent ? 'green' : 'amber'}>
                  {p.consent ? 'Đã xác nhận đồng ý' : 'Chưa xác nhận đồng ý'}
                </Badge>
                <div className="inline-actions">
                  <Button onClick={() => setHistory(p.id)}>Xem mẫu & biểu đồ</Button>
                  {allowed('people', 'edit') && (
                    <Button variant="secondary" onClick={() => setEditing({ ...p })}>
                      Hồ sơ
                    </Button>
                  )}
                </div>
              </div>
            </Panel>
          );
        })}
      </div>
      {history && (
        <Modal
          title={`Các lượt thu · ${personName(history)}`}
          wide
          onClose={() => setHistory(null)}
        >
          <div className="identity-sample-list">
            {catalog.samples
              .filter((v) => v.person === history)
              .map((v) => (
                <button
                  className="list-row"
                  key={v.id}
                  onClick={() => {
                    setView(v);
                    setHistory(null);
                  }}
                >
                  <div>
                    <strong>{v.name}</strong>
                    <small className="cell-sub">{v.date}</small>
                  </div>
                  <span>{v.rowCount} dòng</span>
                  <span className="text-link">Xem tín hiệu ↗</span>
                </button>
              ))}
          </div>
          {!catalog.samples.some((v) => v.person === history) && (
            <Empty
              title="Chưa có nhãn mẫu khớp hồ sơ"
              description="Không tự gán những nhãn không rõ ràng cho người này."
            />
          )}
        </Modal>
      )}
      {view && <SampleViewer sample={view} onClose={() => setView(null)} />}
      {editing && (
        <Modal title={`Hồ sơ · ${editing.name}`} onClose={() => setEditing(null)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mockService.update((v) => ({
                ...v,
                people: v.people.map((p) => (p.id === editing.id ? editing : p)),
              }));
              audit(role, 'Cập nhật ghi chú hồ sơ giao diện', editing.id);
              setEditing(null);
              notify('Đã lưu hồ sơ trên trình duyệt. Không thay đổi data/.');
            }}
          >
            <Notice>
              Tên và mã danh tính được giữ cố định. Chỉ lưu ghi chú/đồng ý trong trình duyệt, không
              sửa metadata gốc.
            </Notice>
            <Field label="Họ tên">
              <input readOnly value={editing.name} />
            </Field>
            <Field label="Ghi chú hồ sơ">
              <textarea
                value={editing.note}
                onChange={(e) => setEditing({ ...editing, note: e.target.value })}
              />
            </Field>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={editing.consent}
                onChange={(e) => setEditing({ ...editing, consent: e.target.checked })}
              />
              Đã ghi nhận đồng ý tham gia
            </label>
            <div className="modal-footer">
              <Button type="submit">Lưu hồ sơ cục bộ</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

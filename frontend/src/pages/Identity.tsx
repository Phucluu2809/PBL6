import { useEffect, useState } from 'react';
import { Fingerprint, ScanLine, ArrowRight, Check } from 'lucide-react';
import { useStore } from '../services/store';
import { useDataset, useSampleDetail, personName } from '../services/dataset';
import { useApp } from '../context';
import DatasetCharts from '../components/DatasetCharts';
import {
  Avatar,
  Badge,
  Button,
  Empty,
  Field,
  Notice,
  PageTitle,
  Panel,
  Tabs,
} from '../components/ui';
export default function Identity() {
  const s = useStore();
  const { catalog, loading, error } = useDataset();
  const { notify } = useApp();
  const [tab, setTab] = useState('Nhận diện danh tính');
  const [sample, setSample] = useState('');
  const [model, setModel] = useState(s.models.find((m) => m.active)?.id ?? '');
  const [candidates, setCandidates] = useState<string[]>([]);
  const detail = useSampleDetail(sample || null);
  const selected = catalog.samples.find((v) => v.id === sample);
  useEffect(() => {
    if (!sample && catalog.samples.length)
      setSample(
        catalog.samples.find((v) => v.person !== 'UNASSIGNED' && (v.rowCount ?? 0) > 0)?.id ??
          catalog.samples[0].id,
      );
  }, [catalog, sample]);
  return (
    <>
      <PageTitle
        eyebrow="BODY ODOR IDENTITY / NHẬN DIỆN"
        title="Nhận diện bằng mùi cơ thể"
        description="Thay ảnh khuôn mặt bằng chuỗi tín hiệu mùi; đối chiếu với các hồ sơ danh tính đã đăng ký."
        actions={
          <Badge tone="purple">
            <Fingerprint size={12} />
            03 hồ sơ tham chiếu
          </Badge>
        }
      />
      <div className="identity-grid">
        {s.people.map((p) => (
          <div
            className={`identity-reference ${selected?.person === p.id ? 'selected' : ''}`}
            key={p.id}
          >
            <Avatar name={p.name} />
            <div>
              <strong>{p.name}</strong>
              <small>
                {catalog.samples.filter((v) => v.person === p.id).length} lượt đã ghép nhãn
              </small>
            </div>
            {selected?.person === p.id && <Badge tone="purple">Nhãn gốc</Badge>}
          </div>
        ))}
      </div>
      <Notice>
        Dữ liệu cảm biến và prediction.json đã lưu được đọc thật. Chưa có dịch vụ chạy model mới;
        ghép hồ sơ theo nhãn không phải kết quả nhận diện AI.
      </Notice>
      {error && <Notice tone="amber">{error}</Notice>}
      <Tabs
        items={['Nhận diện danh tính', 'Target matching', 'Lịch sử nhận diện']}
        value={tab}
        onChange={setTab}
      />
      {tab === 'Lịch sử nhận diện' ? (
        <Panel title="Kết quả đã lưu trên dữ liệu gốc">
          <p>Chọn lượt thu để đọc prediction.json nếu file đã tồn tại.</p>
          <div className="identity-sample-list">
            {catalog.samples
              .filter((v) => v.person !== 'UNASSIGNED')
              .map((v) => (
                <button
                  key={v.id}
                  className="list-row"
                  onClick={() => {
                    setSample(v.id);
                    setTab('Nhận diện danh tính');
                  }}
                >
                  <strong>{v.name}</strong>
                  <span>{personName(v.person)}</span>
                  <span className="text-link">Xem kết quả đã lưu ↗</span>
                </button>
              ))}
          </div>
        </Panel>
      ) : (
        <>
          <div className="two-columns">
            <Panel
              title={tab === 'Target matching' ? 'Mẫu tham chiếu & ứng viên' : 'Mẫu cần nhận diện'}
              description="Chọn từ các lượt thu thật, không tạo tín hiệu giả"
            >
              <div className="padded">
                <Field label="Lượt thu">
                  <select
                    value={sample}
                    disabled={loading}
                    onChange={(e) => {
                      setSample(e.target.value);
                      setCandidates((v) => v.filter((id) => id !== e.target.value));
                    }}
                  >
                    <option value="">Chọn mẫu…</option>
                    {catalog.samples
                      .filter((v) => (v.rowCount ?? 0) > 0)
                      .map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.name} · {personName(v.person)}
                        </option>
                      ))}
                  </select>
                </Field>
                <Field label="Model dự kiến khi tích hợp">
                  <select value={model} onChange={(e) => setModel(e.target.value)}>
                    {s.models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} · {m.version}
                      </option>
                    ))}
                  </select>
                </Field>
                <Notice>
                  Schema mẫu: {selected?.schema ?? 'Chưa chọn'} ·{' '}
                  {selected?.channels?.map((c) => c.label).join(', ') || 'Chưa có kênh'}. Cần xác
                  minh tương thích schema/model trước khi suy luận.
                </Notice>
                {tab === 'Target matching' && (
                  <>
                    <p className="field-title">Chọn tối đa 5 lượt ứng viên</p>
                    <div className="candidate-list">
                      {catalog.samples
                        .filter((v) => v.id !== sample && v.person !== 'UNASSIGNED')
                        .map((v) => (
                          <label key={v.id}>
                            <input
                              type="checkbox"
                              checked={candidates.includes(v.id)}
                              disabled={!candidates.includes(v.id) && candidates.length >= 5}
                              onChange={(e) =>
                                setCandidates((ids) =>
                                  e.target.checked
                                    ? [...ids, v.id]
                                    : ids.filter((id) => id !== v.id),
                                )
                              }
                            />
                            {v.name}
                          </label>
                        ))}
                    </div>
                  </>
                )}
                <Button
                  variant="secondary"
                  onClick={() =>
                    notify(
                      'Đã có giao diện chọn mẫu và model. Cần tích hợp dịch vụ AI để nhận diện mới; không tạo điểm giả.',
                    )
                  }
                >
                  <ScanLine size={16} />
                  Nhận diện mới · chờ tích hợp AI
                </Button>
              </div>
            </Panel>
            <Panel
              title="Kết quả nhận diện"
              description="Chỉ hiện kết quả thực sự có trên file gốc"
            >
              {detail.loading ? (
                <div className="empty">
                  <div className="spinner" />
                  <p>Đang đọc kết quả…</p>
                </div>
              ) : detail.error ? (
                <Notice tone="amber">{detail.error}</Notice>
              ) : detail.data?.prediction ? (
                <div className="padded">
                  <Badge tone="green">ĐỌC TỪ PREDICTION.JSON</Badge>
                  <pre className="json-view">{JSON.stringify(detail.data.prediction, null, 2)}</pre>
                </div>
              ) : (
                <div className="identity-awaiting">
                  <Fingerprint size={55} strokeWidth={1} />
                  <h2>Chưa có kết quả nhận diện</h2>
                  <p>
                    Không suy ra danh tính từ nhãn mẫu hoặc hình dạng biểu đồ. Khi tích hợp model,
                    vùng này sẽ hiển thị người khớp, score, threshold, margin hoặc Unknown.
                  </p>
                  <Badge tone="neutral">AWAITING INFERENCE</Badge>
                </div>
              )}
            </Panel>
          </div>
          {sample && (
            <Panel
              title={`Tín hiệu mẫu · ${selected?.name ?? sample}`}
              description="Dữ liệu thật dùng làm đầu vào, đọc từ raw.csv"
            >
              <DatasetCharts id={sample} />
            </Panel>
          )}
          {tab === 'Target matching' && candidates.length > 0 && (
            <Panel
              title="Các ứng viên đã chọn"
              description="Đối chiếu trực quan, chưa tính similarity hoặc distance"
            >
              <div className="compare-grid padded">
                {catalog.samples
                  .filter((v) => candidates.includes(v.id))
                  .map((v) => (
                    <Panel key={v.id} title={v.name} description={personName(v.person)}>
                      <DatasetCharts id={v.id} compact />
                    </Panel>
                  ))}
              </div>
            </Panel>
          )}
        </>
      )}
    </>
  );
}

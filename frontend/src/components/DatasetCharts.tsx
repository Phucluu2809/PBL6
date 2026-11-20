import { useEffect, useState } from 'react';
import { LockKeyhole, RefreshCw } from 'lucide-react';
import { useSampleDetail, type DatasetDetail, type SignalPoint } from '../services/dataset';
import { Badge, Button, Empty, Notice, Panel, Select } from './ui';

const phaseColors: Record<string, string> = {
  BASELINE: '#e4edf8',
  EXPOSURE: '#efe4fb',
  RECOVERY: '#e1f2eb',
};
export function RawSignalChart({
  data,
  channel,
  phase = 'Tất cả pha',
}: {
  data: DatasetDetail;
  channel: string;
  phase?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const info = data.channels.find((c) => c.key === channel);
  const points = data.points.filter((p) => phase === 'Tất cả pha' || p.phase === phase);
  const finite = points.filter(
    (p) => p.values[channel] !== null && p.values[channel] !== undefined,
  );
  if (!info || !finite.length)
    return (
      <Empty
        title="Kênh không có dữ liệu hợp lệ"
        description="Giá trị thiếu hoặc không đạt cờ hợp lệ được giữ là khoảng trống."
      />
    );
  const lo = finite.reduce((v, p) => Math.min(v, p.values[channel]!), Infinity);
  const hi = finite.reduce((v, p) => Math.max(v, p.values[channel]!), -Infinity);
  const pad = Math.max((hi - lo) * 0.12, Math.abs(hi) * 0.005, 0.0001);
  const min = lo - pad,
    max = hi + pad;
  const t0 = points[0].t,
    t1 = points[points.length - 1].t;
  const width = 720,
    height = 255;
  const left = 77,
    right = 18,
    top = 24,
    bottom = 38;
  const x = (t: number) => left + ((t - t0) / Math.max(1, t1 - t0)) * (width - left - right);
  const y = (v: number) => top + ((max - v) / (max - min)) * (height - top - bottom);
  let path = '',
    pen = false;
  let previous: SignalPoint | null = null;
  for (const p of points) {
    const v = p.values[channel];
    if (v === null || v === undefined) {
      pen = false;
      previous = p;
      continue;
    }
    if (previous && p.t - previous.t > 3) pen = false;
    path += `${pen ? 'L' : 'M'}${x(p.t).toFixed(2)},${y(v).toFixed(2)} `;
    pen = true;
    previous = p;
  }
  const index =
    hover === null
      ? null
      : Math.min(points.length - 1, Math.max(0, Math.round(hover * (points.length - 1))));
  const picked = index === null ? null : points[index];
  return (
    <div className="real-chart">
      <div className="real-chart-caption">
        <strong>{info.label}</strong>
        <span>{info.unit} · tín hiệu gốc, lọc theo cờ hợp lệ</span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${info.label}: tín hiệu thật từ raw.csv, đơn vị ${info.unit}`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const bounds = e.currentTarget.getBoundingClientRect();
          const px = ((e.clientX - bounds.left) / bounds.width) * width;
          const target =
            t0 + Math.max(0, Math.min(1, (px - left) / (width - left - right))) * (t1 - t0);
          let best = 0;
          for (let i = 1; i < points.length; i++)
            if (Math.abs(points[i].t - target) < Math.abs(points[best].t - target)) best = i;
          setHover(best / Math.max(1, points.length - 1));
        }}
      >
        <desc>
          Không nội suy qua lỗi hoặc khoảng mất dữ liệu quá 3 giây. Trục thời gian tính từ dòng đầu
          của file.
        </desc>
        {data.segments
          .filter(
            (s) => (phase === 'Tất cả pha' || phase === s.phase) && s.end >= t0 && s.start <= t1,
          )
          .map((s, i) => (
            <g key={i}>
              <rect
                x={x(Math.max(t0, s.start))}
                y={top}
                width={Math.max(1, x(Math.min(t1, s.end)) - x(Math.max(t0, s.start)))}
                height={height - top - bottom}
                fill={phaseColors[s.phase] ?? '#f8f7fa'}
              />
              {['BASELINE', 'EXPOSURE', 'RECOVERY'].includes(s.phase) && (
                <text x={x(Math.max(t0, s.start)) + 5} y={top + 12} className="phase-label">
                  {s.phase}
                </text>
              )}
            </g>
          ))}
        {Array.from({ length: 5 }, (_, i) => {
          const v = min + ((max - min) * i) / 4;
          return (
            <g key={i}>
              <line
                x1={left}
                y1={y(v)}
                x2={width - right}
                y2={y(v)}
                stroke="#dcd8e5"
                strokeDasharray="3 4"
              />
              <text x={left - 9} y={y(v) + 4} textAnchor="end">
                {v.toLocaleString('en-US', { maximumFractionDigits: Math.abs(v) < 10 ? 3 : 1 })}
              </text>
              <text x={left + ((width - left - right) * i) / 4} y={height - 12} textAnchor="middle">
                {(t0 + ((t1 - t0) * i) / 4).toFixed(0)}s
              </text>
            </g>
          );
        })}
        <path d={path} stroke="#8662c4" strokeWidth="1.7" fill="none" />
        {finite.length === 1 && (
          <circle cx={x(finite[0].t)} cy={y(finite[0].values[channel]!)} r="3" fill="#8662c4" />
        )}
        {picked && (
          <line
            x1={x(picked.t)}
            x2={x(picked.t)}
            y1={top}
            y2={height - bottom}
            stroke="#5c497a"
            strokeDasharray="3 3"
          />
        )}
      </svg>
      <div className="signal-inspector">
        {picked ? (
          <>
            <strong>{picked.t.toFixed(2)}s</strong>
            <span>{picked.phase}</span>
            <span>
              {picked.values[channel] === null
                ? 'Không hợp lệ / thiếu'
                : picked.values[channel]?.toLocaleString('vi-VN', {
                    maximumFractionDigits: 4,
                  })}{' '}
              {info.unit}
            </span>
          </>
        ) : (
          <span>Di chuột trên biểu đồ để xem thời điểm, pha và giá trị.</span>
        )}
      </div>
    </div>
  );
}
export default function DatasetCharts({ id, compact = false }: { id: string; compact?: boolean }) {
  const { data, loading, error } = useSampleDetail(id);
  const [channel, setChannel] = useState('');
  const [phase, setPhase] = useState('Tất cả pha');
  useEffect(() => {
    setChannel('');
    setPhase('Tất cả pha');
  }, [id]);
  if (loading)
    return (
      <div className="empty" role="status">
        <div className="spinner" />
        <p>Đang đọc raw.csv…</p>
      </div>
    );
  if (error) return <Notice tone="amber">{error}</Notice>;
  if (!data) return null;
  const selected = data.channels.find((c) => c.key === channel) ?? data.channels[0];
  if (!selected)
    return (
      <Empty
        title="File chưa có tín hiệu hợp lệ"
        description={`${data.rowCount} dòng trong raw.csv. Xem metadata và QC để kiểm tra.`}
      />
    );
  return (
    <>
      <div className="real-chart-toolbar">
        <Select
          label="Kênh cảm biến"
          value={selected.key}
          onChange={setChannel}
          options={data.channels.map((c) => c.key)}
        />
        {!compact && (
          <Select
            label="Pha tín hiệu"
            value={phase}
            onChange={setPhase}
            options={['Tất cả pha', ...new Set(data.points.map((p) => p.phase))]}
          />
        )}
        <Badge tone="green">
          <LockKeyhole size={11} />
          RAW · CHỈ ĐỌC
        </Badge>
      </div>
      <RawSignalChart data={data} channel={selected.key} phase={phase} />
      {!compact && (
        <>
          <div className="signal-metrics">
            <div>
              <small>Giá trị nhỏ nhất</small>
              <strong>
                {selected.min.toLocaleString('vi-VN', { maximumFractionDigits: 4 })} {selected.unit}
              </strong>
            </div>
            <div>
              <small>Giá trị lớn nhất</small>
              <strong>
                {selected.max.toLocaleString('vi-VN', { maximumFractionDigits: 4 })} {selected.unit}
              </strong>
            </div>
            <div>
              <small>Trung bình hợp lệ</small>
              <strong>
                {selected.mean.toLocaleString('vi-VN', { maximumFractionDigits: 4 })}{' '}
                {selected.unit}
              </strong>
            </div>
            <div>
              <small>Hợp lệ / không hợp lệ</small>
              <strong>
                {selected.count} / {selected.invalid}
              </strong>
            </div>
          </div>
          <p className="chart-note">
            Thống kê tính trên toàn file raw.csv; bộ lọc pha chỉ đổi biểu đồ. Không làm mượt, không
            điền giá trị lỗi bằng 0; đường biểu diễn ngắt khi dữ liệu thiếu hoặc khoảng cách &gt; 3
            giây.
          </p>
        </>
      )}
    </>
  );
}
export function SampleEvidence({ id, tab }: { id: string; tab: string }) {
  const { data, loading, error } = useSampleDetail(id);
  if (loading)
    return (
      <div className="empty">
        <div className="spinner" />
        <p>Đang đọc hồ sơ gốc…</p>
      </div>
    );
  if (error) return <Notice tone="amber">{error}</Notice>;
  if (!data) return null;
  return (
    <div className="padded">
      <Notice>
        Chỉ đọc tài liệu đang có. COMPLETE là trạng thái quy trình, không đồng nghĩa QC PASS.
      </Notice>
      {tab === 'QC & metadata' ? (
        <>
          <h3>Kết quả tổng hợp gốc · summary.json</h3>
          <pre className="json-view">
            {data.summary ? JSON.stringify(data.summary, null, 2) : 'Không có summary.json'}
          </pre>
          <h3>Metadata gốc · metadata.json</h3>
          <pre className="json-view">
            {data.metadata ? JSON.stringify(data.metadata, null, 2) : 'Không có metadata.json'}
          </pre>
        </>
      ) : tab === 'Nhận diện' ? (
        <>
          <h3>Kết quả đã có · prediction.json</h3>
          {data.prediction ? (
            <pre className="json-view">{JSON.stringify(data.prediction, null, 2)}</pre>
          ) : (
            <Empty
              title="Chưa có kết quả nhận diện thật"
              description="Chưa tìm thấy prediction.json cạnh mẫu. Giao diện không tự gán danh tính từ hình dạng tín hiệu."
            />
          )}
        </>
      ) : (
        <>
          <dl className="detail-list">
            <div>
              <dt>Số dòng raw</dt>
              <dd>{data.rowCount}</dd>
            </div>
            <div>
              <dt>SHA-256 hiện tại</dt>
              <dd className="hash-value">{data.sha256}</dd>
            </div>
            <div>
              <dt>Cột dữ liệu</dt>
              <dd>{data.columns.join(', ')}</dd>
            </div>
          </dl>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Pha</th>
                  <th>Bắt đầu</th>
                  <th>Kết thúc</th>
                  <th>Thời lượng quan sát</th>
                </tr>
              </thead>
              <tbody>
                {data.segments.map((v, i) => (
                  <tr key={i}>
                    <td>{v.phase}</td>
                    <td>{v.start.toFixed(2)}s</td>
                    <td>{v.end.toFixed(2)}s</td>
                    <td>{Math.max(0, v.end - v.start).toFixed(2)}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

import { useEffect, useState } from 'react';
import { BrainCircuit, Play, Sparkles, Check, Plus } from 'lucide-react';
import { useStore, mockService, audit } from '../services/store';
import { useApp } from '../context';
import type { AIResult } from '../types';
import {
  Badge,
  Button,
  Confirm,
  Empty,
  Field,
  Modal,
  Notice,
  PageTitle,
  Panel,
  Tabs,
} from '../components/ui';
export function Models() {
  const s = useStore();
  const { role, allowed, notify } = useApp();
  const [confirm, setConfirm] = useState<string | null>(null);
  const [details, setDetails] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [name, setName] = useState('');
  const [version, setVersion] = useState('');
  const [channels, setChannels] = useState('');
  return (
    <>
      <PageTitle
        eyebrow="AI / MODEL REGISTRY"
        title="Thư viện mô hình"
        description="Theo dõi phiên bản, schema đầu vào và trạng thái kích hoạt."
        actions={
          allowed('models', 'manage') && (
            <Button onClick={() => setImporting(true)}>
              <Plus size={16} />
              Đăng ký model demo
            </Button>
          )
        }
      />
      <Notice>
        Đăng ký model chỉ lưu metadata, không tải hoặc thực thi file mô hình. Kiểm tra schema trước
        khi tích hợp pipeline thật.
      </Notice>
      <div className="cards-grid">
        {s.models.map((m) => (
          <Panel key={m.id}>
            <div className="model-card">
              <div className="model-icon">
                <BrainCircuit size={27} />
              </div>
              <Badge tone={m.active ? 'green' : 'neutral'}>
                {m.active ? 'Đang kích hoạt' : 'Chưa kích hoạt'}
              </Badge>
              <h2>{m.name}</h2>
              <p className="muted">
                Phiên bản {m.version} · {m.date}
              </p>
              <p>{m.channels}</p>
              <p className="muted">{m.metrics}</p>
              <div className="inline-actions">
                <Button variant="secondary" onClick={() => setDetails(m.id)}>
                  Xem chi tiết
                </Button>
                {allowed('models', 'manage') && (
                  <Button variant={m.active ? 'ghost' : 'primary'} onClick={() => setConfirm(m.id)}>
                    {m.active ? (
                      'Hủy kích hoạt'
                    ) : (
                      <>
                        <Check size={14} />
                        Kích hoạt
                      </>
                    )}
                  </Button>
                )}
              </div>
            </div>
          </Panel>
        ))}
      </div>
      {details && (
        <Modal title="Chi tiết model" onClose={() => setDetails(null)}>
          {s.models
            .filter((m) => m.id === details)
            .map((m) => (
              <dl className="detail-list" key={m.id}>
                {Object.entries(m).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{String(v)}</dd>
                  </div>
                ))}
              </dl>
            ))}
        </Modal>
      )}
      {confirm && (
        <Confirm
          title="Thay đổi model active?"
          description="Chỉ một model được active trong bản demo. Thao tác sẽ được ghi audit."
          onClose={() => setConfirm(null)}
          onConfirm={() => {
            mockService.update((v) => ({
              ...v,
              models: v.models.map((m) => ({ ...m, active: m.id === confirm ? !m.active : false })),
            }));
            audit(role, 'Thay đổi model active', confirm);
            notify('Đã cập nhật model active trong demo.');
          }}
        />
      )}
      {importing && (
        <Modal title="Đăng ký metadata model demo" onClose={() => setImporting(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mockService.update((v) => ({
                ...v,
                models: [
                  ...v.models,
                  {
                    id: crypto.randomUUID(),
                    name: name.trim(),
                    version,
                    channels,
                    metrics: 'Metadata do người dùng nhập · chưa kiểm định',
                    active: false,
                    date: new Date().toLocaleDateString('vi-VN'),
                  },
                ],
              }));
              audit(role, 'Đăng ký metadata model', name);
              setImporting(false);
              notify('Đã thêm metadata model demo.');
            }}
          >
            <Field label="Tên model">
              <input required value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Phiên bản">
              <input required value={version} onChange={(e) => setVersion(e.target.value)} />
            </Field>
            <Field label="Schema / kênh đầu vào">
              <textarea required value={channels} onChange={(e) => setChannels(e.target.value)} />
            </Field>
            <div className="modal-footer">
              <Button type="submit">Lưu metadata</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

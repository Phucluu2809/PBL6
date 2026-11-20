"""Read-only QC and conversion of one recording to a six-channel tensor."""

import csv
import hashlib
import json
import unicodedata
from pathlib import Path

import numpy as np

from processing.core.signals import CHANNELS, flag, validity

SIGNALS = tuple((key, sensor) for key, _, _, sensor in CHANNELS if key in {
    'tgs2602_voltage_v', 'mq3_1_voltage_v', 'mq135_2_voltage_v',
    'mq3_2_voltage_v', 'gas_resistance_ohm', 'humidity_pct',
})
PHASES = {'BASELINE': 60, 'EXPOSURE': 120}
DRIFT_LIMIT = 5.0


def identity(folder):
    key = ''.join(c for c in unicodedata.normalize('NFD', folder.casefold())
                  if not unicodedata.combining(c)).replace('đ', 'd')
    if key in ('cf', 'kk_baseline'):
        return None, key
    suffix = next((s for s in ('_itcoffe', '_itcf', '_coffee', '_coffe', '_cf')
                   if key.endswith(s)), '')
    key = key[:-len(suffix)] if suffix else key
    key = {'aduong': 'duong', 'anhduong': 'duong', 'phucluu': 'phuc'}.get(key, key)
    display = {'duong': 'Dương', 'phuc': 'Phúc', 'tai': 'Tài'}
    condition = 'light_coffee' if suffix.startswith('_it') else 'coffee' if suffix else 'normal'
    return display.get(key, key), condition


def phase_values(rows, phase, count):
    selected = [row for row in rows if row.get('phase') == phase]
    if len(selected) != count:
        raise ValueError(f'{phase}: cần {count} điểm, có {len(selected)}.')
    times = np.array([float(row['mono_s']) for row in selected])
    if not np.isfinite(times).all() or not np.all(np.abs(np.diff(times)-1) <= 0.1):
        raise ValueError(f'{phase}: mốc thời gian không đều ở 1 Hz.')
    return selected, times


def values(rows, phase):
    output = []
    for key, sensor in SIGNALS:
        if any(validity(row, key, sensor, True) is not True for row in rows):
            raise ValueError(f'{phase}: {key} thiếu dữ liệu hoặc cờ hợp lệ.')
        output.append([float(row[key]) for row in rows])
    result = np.asarray(output, dtype=np.float64)
    if np.any(result[:5] <= 0) or np.any((result[5] < 0) | (result[5] > 100)):
        raise ValueError(f'{phase}: có giá trị ngoài miền vật lý.')
    return result


def unstable(trace, times):
    centered = times - times.mean()
    slope = (trace @ centered) / np.dot(centered, centered)
    median = np.median(trace, axis=1)
    return np.maximum(abs(slope)*60, np.ptp(trace, axis=1))*100/median


def prepare(folder, info, *, baseline_warn=False):
    raw = Path(folder) / 'raw.csv'
    meta = json.loads(raw.with_name('metadata.json').read_text(encoding='utf-8-sig'))
    with raw.open('r', encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle, strict=True))
    info.update(trial_id=meta.get('trial_id'), session=meta.get('session_id'),
                day=str(meta.get('started_at') or (rows[0].get('timestamp') if rows else '') or '')[:10],
                config_hash=meta.get('config_hash'), sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
    schema = meta.get('schema') or (rows[0].get('schema') if rows else None)
    if schema != 'robonose.dataset.v1' or meta.get('status') != 'COMPLETE':
        raise ValueError(f'Schema/trạng thái không dùng được: {schema}/{meta.get("status")}.')
    if not all(info.get(key) for key in ('trial_id', 'session', 'day')):
        raise ValueError('Thiếu trial_id, session_id hoặc ngày đo.')
    baseline, bt = phase_values(rows, 'BASELINE', PHASES['BASELINE'])
    exposure, et = phase_values(rows, 'EXPOSURE', PHASES['EXPOSURE'])
    period = np.asarray([float(row['mono_s']) for row in rows])
    if not np.isfinite(period).all() or np.any(np.diff(period) <= 0):
        raise ValueError('Timestamp toàn lượt không tăng đều theo thứ tự ghi.')
    b = values(baseline, 'BASELINE')
    x = values(exposure, 'EXPOSURE')
    if np.any(np.ptp(x[:5], axis=1) == 0):
        raise ValueError('Có kênh khí giữ nguyên suốt exposure.')
    reference = np.median(b[:, -30:], axis=1)
    drift = unstable(b[:5, -30:], bt[-30:])
    info['baseline_drift'] = dict(zip((key for key, _ in SIGNALS[:5]), drift.round(3)))
    warnings = info.setdefault('warnings', [])
    if info.get('condition') not in ('cf', 'kk_baseline') and np.any(drift > DRIFT_LIMIT):
        message = 'Nền 30 giây cuối vượt 5%/phút hoặc biên độ 5% ở kênh khí.'
        if not baseline_warn:
            raise ValueError(message)
        warnings.append(message)
    pre = [row for row, time in zip(rows, period)
           if et[0]-30 <= time < et[0] and row.get('phase') in ('BASELINE', 'WAIT_EXPOSURE')]
    if len(pre) >= 24:
        try:
            before = values(pre, 'Trước exposure')
            times = np.asarray([float(row['mono_s']) for row in pre])
            if np.any(unstable(before[:5], times) > DRIFT_LIMIT):
                warnings.append('Tín hiệu còn trôi ngay trước exposure.')
            if np.any(abs(np.median(before[:5], axis=1)/reference[:5]-1) > .05):
                warnings.append('Tín hiệu trước exposure lệch trên 5% so với nền.')
        except ValueError as exc:
            warnings.append(str(exc))
    if any(flag(row.get('context_straddled')) is True for row in exposure):
        warnings.append('Có điểm exposure nằm gần lúc chuyển ngữ cảnh thu.')
    delta = x - reference[:, None]
    delta[4] = np.log(x[4] / reference[4])
    return delta.astype(np.float32)

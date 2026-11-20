"""Inspect original sensor recordings. Values remain untouched, including invalid ones."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from pathlib import Path

CHANNELS = (
    ('tgs2602_voltage_v', 'TGS2602', 'V', 'tgs2602'),
    ('mq135_voltage_v', 'MQ135', 'V', 'mq135'),
    ('mq3_voltage_v', 'MQ3', 'V', 'mq3'),
    ('mq135_1_voltage_v', 'MQ135 #1', 'V', 'mq135_1'),
    ('mq3_1_voltage_v', 'MQ3 #1', 'V', 'mq3_1'),
    ('mq135_2_voltage_v', 'MQ135 #2', 'V', 'mq135_2'),
    ('mq3_2_voltage_v', 'MQ3 #2', 'V', 'mq3_2'),
    ('gas_resistance_ohm', 'BME gas', 'Ω', 'gas'),
    ('temperature_c', 'Nhiệt độ', '°C', 'environment'),
    ('humidity_pct', 'Độ ẩm', '%RH', 'environment'),
    ('pressure_hpa', 'Áp suất', 'hPa', 'environment'),
)


def digest(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def flag(value):
    text = str(value).strip().lower()
    if text in ('true', '1', 'yes', 'on'):
        return True
    if text in ('false', '0', 'no', 'off'):
        return False
    return None


def read_json(path: Path):
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def validity(row, key, sensor, modern):
    if number(row.get(key)) is None:
        return False
    prefix = ('bme688' if modern else 'bme') if sensor in ('gas', 'environment') else sensor
    status = row.get(prefix + '_status', '')
    flags = [flag(row.get(prefix + '_fresh'))]
    if modern:
        flags.append(flag(row.get(prefix + '_valid')))
    if status and status != 'OK':
        return False
    if sensor == 'gas':
        flags.extend(flag(row.get(k)) for k in ('gas_valid', 'heater_stable', 'new_data'))
    if any(word in row.get(prefix + '_quality', '') for word in ('NEGATIVE', 'ADC_LIMIT')):
        return False
    if False in flags:
        return False
    if not status or None in flags:
        return None
    return True


def weighted_coverage(chunks, key, period, valid_only=False):
    covered = denominator = 0.0
    for chunk in chunks:
        timed = [p for p in chunk if p['t'] is not None]
        if len(timed) < 2:
            continue
        duration = timed[-1]['t'] - timed[0]['t']
        if duration <= 0:
            continue
        denominator += duration
        for left, right in zip(chunk, chunk[1:]):
            if left['t'] is None or right['t'] is None or left['values'][key] is None:
                continue
            if valid_only and left['valid'][key] is not True:
                continue
            dt = right['t'] - left['t']
            if dt > 0:
                covered += min(period, dt)
    return min(1.0, max(0.0, covered / denominator)) if denominator else None


def inspect(raw_path: Path, metadata_path: Path) -> dict:
    raw_bytes = raw_path.read_bytes()
    metadata_bytes = metadata_path.read_bytes() if metadata_path.is_file() else None
    result = dict(raw_hash=hashlib.sha256(raw_bytes).hexdigest(),
                  metadata_hash=hashlib.sha256(metadata_bytes).hexdigest() if metadata_bytes is not None else None,
                  row_count=0, points=[], channels=[], segments=[], warnings=[], error=None,
                  sampling_rate=None, expected_rate=None, median_interval=None, max_gap=None,
                  duration=0, time_errors=0, missing_times=0, missing_sequence=0,
                  duplicate_sequence=0, metadata=None)
    warnings = result['warnings']
    try:
        metadata = json.loads(metadata_bytes.decode('utf-8-sig')) if metadata_bytes is not None else {}
        if not isinstance(metadata, dict):
            raise ValueError('metadata must be object')
    except (ValueError, UnicodeError):
        metadata = {}
        warnings.append('metadata.json không hợp lệ; không tự đoán cấu hình.')
    result['metadata'] = metadata
    if metadata_bytes is None:
        warnings.append('Không có metadata.json; cấu hình chưa được xác nhận.')
    try:
        reader = csv.DictReader(io.StringIO(raw_bytes.decode('utf-8-sig'), newline=''), strict=True)
        headers = reader.fieldnames or []
        rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        result['error'] = f'Không đọc được CSV: {exc}'
        return result
    if not headers or len(headers) != len(set(headers)):
        result['error'] = 'Thiếu header hoặc tên cột trùng.'
        return result
    result['columns'] = headers
    result['row_count'] = len(rows)
    if not any(k in headers for k in ('mono_s', 'elapsed_s')):
        result['error'] = 'Chưa hỗ trợ trục thời gian: cần mono_s hoặc elapsed_s.'
        return result
    defs = [c for c in CHANNELS if c[0] in headers]
    if not defs:
        result['error'] = 'Không tìm thấy kênh tín hiệu được hỗ trợ.'
        return result
    config = metadata.get('config', {})
    if not isinstance(config, dict):
        config = {}
    rate = number(config.get('sampling_hz', config.get('sample_hz')))
    rate = rate if rate is not None and rate > 0 else None
    result['expected_rate'] = rate
    modern = 'mono_s' in headers and ('schema' in headers or 'bme688_status' in headers)
    origin = last_time = last_seq = last_boot = None
    dts, chunks, chunk = [], [], []
    malformed = 0
    for index, row in enumerate(rows):
        if None in row or any(v is None for v in row.values()):
            malformed += 1
        t = number(row.get('mono_s', row.get('elapsed_s')))
        seq = number(row.get('seq'))
        boot = row.get('boot_id')
        if t is None:
            result['missing_times'] += 1
        else:
            if origin is None:
                origin = t
            if last_time is not None:
                dt = t - last_time
                if dt <= 0:
                    result['time_errors'] += 1
                else:
                    dts.append(dt)
        changed_boot = last_boot is not None and boot and boot != last_boot
        if changed_boot:
            result['time_errors'] += 1
        if seq is not None and last_seq is not None and not changed_boot:
            if seq == last_seq:
                result['duplicate_sequence'] += 1
            elif seq > last_seq + 1:
                result['missing_sequence'] += int(seq - last_seq - 1)
            elif seq < last_seq:
                result['time_errors'] += 1
        point = dict(t=t - origin if t is not None else None, row=index + 2,
                     phase=row.get('phase') or 'UNKNOWN', segment=f"{boot or ''}:{row.get('segment_id', '')}",
                     seq=row.get('seq'), timestamp=row.get('timestamp'), values={}, valid={})
        for key, _, _, sensor in defs:
            point['values'][key] = number(row.get(key))
            point['valid'][key] = validity(row, key, sensor, modern)
        if chunk:
            prev = chunk[-1]
            backwards = t is not None and last_time is not None and t <= last_time
            if prev['phase'] != point['phase'] or prev['segment'] != point['segment'] or backwards:
                chunks.append(chunk)
                chunk = []
        chunk.append(point)
        result['points'].append(point)
        last_time = t
        if seq is not None:
            last_seq = seq
        if boot:
            last_boot = boot
    if chunk:
        chunks.append(chunk)
    period = statistics.median(dts) if dts else None
    result['median_interval'] = period
    result['sampling_rate'] = 1 / period if period else None
    result['max_gap'] = max(dts, default=None)
    times = [p['t'] for p in result['points'] if p['t'] is not None]
    result['duration'] = max(times) - min(times) if times else 0
    baseline_chunks = [c for c in chunks if c[0]['phase'] == 'BASELINE']
    for chunk in chunks:
        ts = [p['t'] for p in chunk if p['t'] is not None]
        if ts:
            result['segments'].append(dict(phase=chunk[0]['phase'], segment=chunk[0]['segment'],
                                           start=ts[0], end=ts[-1], rows=len(chunk)))
    for key, label, unit, _ in defs:
        values = [p['values'][key] for p in result['points'] if p['values'][key] is not None]
        if not values:
            continue  # Empty legacy aliases are not additional physical channels.
        baseline = [p for p in baseline_chunks[0] if p['valid'][key] is True and p['t'] is not None] if len(baseline_chunks) == 1 else []
        slope = cv = None
        if len(baseline) >= 2:
            xs, ys = [p['t'] for p in baseline], [p['values'][key] for p in baseline]
            mx, my = statistics.mean(xs), statistics.mean(ys)
            denominator = sum((x - mx) ** 2 for x in xs)
            slope = 60 * sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denominator if denominator else None
            center = statistics.median(ys)
            cv = 100 * 1.4826 * statistics.median(abs(y - center) for y in ys) / abs(center) if center else None
        states = [p['valid'][key] for p in result['points']]
        result['channels'].append(dict(key=key, label=label, unit=unit, count=len(values),
            minimum=min(values), maximum=max(values), mean=statistics.mean(values),
            valid_count=sum(s is True for s in states), invalid_count=sum(s is False for s in states),
            unknown_count=sum(s is None for s in states), baseline_slope=slope, baseline_cv=cv,
            observed_coverage=weighted_coverage(chunks, key, 1 / rate if rate else period) if period and not result['time_errors'] else None,
            valid_coverage=weighted_coverage(chunks, key, 1 / rate if rate else period, True) if period and not result['time_errors'] else None))
    if not rate:
        warnings.append('Không có sampling cấu hình; coverage chỉ ước tính theo median Δt, không phải kiểm chứng thu đủ.')
    if malformed:
        warnings.append(f'{malformed} dòng lệch cấu trúc cột.')
    if result['time_errors']:
        warnings.append(f"{result['time_errors']} lỗi thời gian/seq/đổi boot; không tự sắp xếp hoặc sửa.")
    if result['missing_times']:
        warnings.append(f"{result['missing_times']} dòng thiếu thời gian, không vẽ được vị trí trên trục.")
    if any(c['unknown_count'] for c in result['channels']):
        warnings.append('Có cờ validity UNKNOWN; giữ riêng, không tự coi là hợp lệ.')
    if not rows:
        warnings.append('Raw chỉ có header, không có số đo.')
    if not {'BASELINE', 'EXPOSURE', 'RECOVERY'}.issubset({p['phase'] for p in result['points']}):
        warnings.append('Chưa thấy đủ ba pha chính trong raw. Không tự kết luận đạt hoặc loại.')
    return result

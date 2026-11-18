"""Downloadable SVG generated in Python from untouched numeric samples."""
from html import escape

COLORS = {'BASELINE': '#e9f0fb', 'EXPOSURE': '#f0e7fc', 'RECOVERY': '#e5f5ee'}


def svg_chart(detail, key, title):
    channel = next((c for c in detail['channels'] if c['key'] == key), None)
    if channel is None:
        raise ValueError('Kênh không tồn tại.')
    points = [p for p in detail['points'] if p['t'] is not None]
    finite = [p for p in points if p['values'].get(key) is not None]
    if not finite:
        raise ValueError('Không có số đo để vẽ.')
    width, height = 1200, 520
    left, right, top, bottom = 95, 30, 92, 75
    t0, t1 = min(p['t'] for p in points), max(p['t'] for p in points)
    low, high = min(p['values'][key] for p in finite), max(p['values'][key] for p in finite)
    pad = max((high - low) * .1, abs(high) * .005, .0001)
    low, high = low - pad, high + pad
    x = lambda t: left + (t - t0) / max(t1 - t0, 1e-9) * (width - left - right)
    y = lambda v: top + (high - v) / (high - low) * (height - top - bottom)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<g font-family="Segoe UI,Arial,sans-serif" fill="#51475e">',
           f'<text x="{left}" y="32" font-size="21">{escape(title)}</text>',
           f'<text x="{left}" y="58" font-size="13">{escape(channel["label"])} · {escape(channel["unit"])} · RAW — không smoothing</text>']
    for seg in detail['segments']:
        a, b = max(t0, seg['start']), min(t1, seg['end'])
        if b < a:
            continue
        out.append(f'<rect x="{x(a):.2f}" y="{top}" width="{max(1,x(b)-x(a)):.2f}" height="{height-top-bottom}" fill="{COLORS.get(seg["phase"],"#f7f7fa")}"/>')
        out.append(f'<text x="{x(a)+4:.2f}" y="{top+14}" font-size="9">{escape(seg["phase"])}</text>')
    for i in range(5):
        value = low + (high - low) * i / 4
        t = t0 + (t1 - t0) * i / 4
        out.extend([f'<line x1="{left}" y1="{y(value):.2f}" x2="{width-right}" y2="{y(value):.2f}" stroke="#dedbe5" stroke-dasharray="4 5"/>',
                    f'<text x="{left-10}" y="{y(value)+4:.2f}" text-anchor="end" font-size="11">{value:.5g}</text>',
                    f'<text x="{x(t):.2f}" y="{height-48}" text-anchor="middle" font-size="11">{t:.1f}s</text>'])
    path, markers, previous, pen = [], [], None, False
    for point in detail['points']:
        value, t = point['values'].get(key), point['t']
        if value is None or t is None:
            pen, previous = False, point
            continue 
        if previous and (previous['t'] is None or t <= previous['t'] or t - previous['t'] > 3 or point['phase'] != previous['phase'] or point['segment'] != previous['segment']):
            pen = False
        path.append(f'{"L" if pen else "M"}{x(t):.2f},{y(value):.2f}')
        if point['valid'][key] is not True:
            color = '#d45e6e' if point['valid'][key] is False else '#c9973a'
            markers.append(f'<circle cx="{x(t):.2f}" cy="{y(value):.2f}" r="2.7" fill="{color}"/>')
        pen, previous = True, point
    out.extend([f'<path d="{" ".join(path)}" fill="none" stroke="#8260c2" stroke-width="1.6"/>', *markers,
                f'<text x="{left}" y="{height-20}" font-size="10">Đỏ: cờ không hợp lệ · Vàng: chưa xác định · Số đo raw được giữ nguyên.</text>',
                f'<text x="{left}" y="{height-5}" font-size="9">SHA-256: {escape(detail["raw_hash"])}</text>', '</g></svg>'])
    return ''.join(out).encode('utf-8')

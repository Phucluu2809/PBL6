"""Run from the repository root: python -m odor_embed.run."""

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np

from .preprocess import SIGNALS, identity, prepare

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'odor_embed' / 'runs'


def inventory(source, *, baseline_warn=False, exclude_days=()):
    records = []
    for raw in sorted(source.rglob('raw.csv')):
        relative = raw.relative_to(source)
        if len(relative.parts) < 3 or relative.parts[0].startswith(('.', '_')):
            continue
        label, condition = identity(relative.parts[0])
        record = dict(path=relative.parent.as_posix(), label=label, condition=condition)
        try:
            record['tensor'] = prepare(raw.parent, record, baseline_warn=baseline_warn)
            record['qc'] = 'WARN' if record.get('warnings') else 'PASS'
        except (ValueError, TypeError, OSError, KeyError, csv.Error) as exc:
            record.update(qc='REJECT', reason=str(exc))
        if record.get('day') in exclude_days:
            record.pop('tensor', None)
            record.update(qc='EXCLUDED_DAY', reason=f'Bỏ ngày {record["day"]} theo cấu hình.')
        records.append(record)
    for key in ('trial_id', 'sha256'):
        matches = defaultdict(list)
        for record in records:
            if record.get(key):
                matches[record[key]].append(record)
        for group in matches.values():
            usable = [record for record in group if 'tensor' in record]
            if len(usable) < 2:
                continue
            same_label = len({(r['label'], r['condition']) for r in usable}) == 1
            for duplicate in usable[1:] if same_label else usable:
                duplicate.pop('tensor')
                duplicate.update(qc='REJECT', reason=f'Trùng {key}' if same_label else f'Trùng {key} nhưng khác nhãn hoặc điều kiện')
    return records


def grouped_split(records, key, rng):
    """Pick a deterministic holdout while retaining every enrolled label in train."""
    group_labels = defaultdict(set)
    for r in records:
        group_labels[r[key]].add(r['label'])
    groups = sorted(group_labels)
    labels = {r['label'] for r in records}
    group_counts = Counter(label for names in group_labels.values() for label in names)
    candidates = [g for g in groups if all(group_counts[label] > 1 for label in group_labels[g])]
    target = max(1, round(len(records)*.2))
    max_groups = max(1, round(len(groups)*.3))
    best = set()
    best_score = (0, -target)
    for _ in range(256):
        held = set()
        for group in rng.permutation(candidates):
            held.add(str(group))
            remaining = set().union(*(group_labels[g] for g in groups if g not in held))
            if remaining != labels:
                held.remove(str(group))
                continue
            test_rows = [r for r in records if r[key] in held]
            score = (len({r['label'] for r in test_rows}), -abs(len(test_rows)-target))
            if score > best_score:
                best, best_score = held.copy(), score
            if len(held) >= max_groups:
                break
    return best


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def per_label_holdout(records, *, one_per_day=False):
    """Choose a deterministic holdout per label, optionally one recording per day."""
    by_label = defaultdict(list)
    for row in records:
        by_label[row['label'] or row['condition']].append(row)
    held = set()
    for rows in by_label.values():
        if len(rows) == 1:
            continue
        rows.sort(key=lambda r: (r['day'], r['path']), reverse=True)
        if one_per_day:
            by_day = {}
            for row in rows:
                by_day.setdefault(row['day'], row['path'])
            candidates = list(by_day.values())
            # If every day contains a single recording, retain the oldest one.
            held.update(candidates[:len(rows)-1])
            continue
        target = max(1, len(rows) // 5)
        sessions = defaultdict(list)
        for row in rows:
            sessions[row['session']].append(row['path'])
        # Select whole sessions when they add up to the desired count.
        choices = {0: []}
        for paths in sessions.values():
            for count, selected in list(choices.items()):
                total = count + len(paths)
                if total <= target and total not in choices:
                    choices[total] = selected + paths
        held.update(choices.get(target, [r['path'] for r in rows[:target]]))
    return held


def train(args):
    source = args.data.resolve(strict=True)
    output_base = RUNS.resolve()
    if output_base != RUNS or source == output_base or source in output_base.parents or output_base in source.parents:
        raise ValueError('Nguồn và thư mục kết quả phải nằm ở hai cây riêng.')
    exclude_days = set(getattr(args, 'exclude_days', ()))
    test_days = set(getattr(args, 'test_days', ()))
    one_per_day = getattr(args, 'per_label_day', False)
    split_per_label = getattr(args, 'per_label', False) or one_per_day
    if split_per_label and (args.all_data or test_days):
        raise ValueError('Chia theo nhãn cần all_data=False và không dùng ngày test cố định.')
    if test_days & exclude_days:
        raise ValueError('Ngày test không được trùng với ngày bỏ qua.')
    if test_days and (args.all_data or args.group_by != 'day'):
        raise ValueError('Ngày test cố định cần group_by=day và all_data=False.')
    records = inventory(source, baseline_warn=args.baseline_warn, exclude_days=exclude_days)
    people = [r for r in records if 'tensor' in r and r['label']]
    labels = sorted({r['label'] for r in people})
    rng = np.random.default_rng(args.seed)
    key = args.group_by
    if split_per_label:
        held = set()
    elif test_days:
        missing_days = test_days - {row['day'] for row in people}
        if missing_days:
            raise ValueError('Ngày test không có lượt người hợp lệ: ' + ', '.join(sorted(missing_days)))
        held = test_days
        missing_labels = set(labels) - {row['label'] for row in people if row['day'] not in held}
        if missing_labels:
            raise ValueError('Các nhãn sau chỉ có trong ngày test: ' + ', '.join(sorted(missing_labels)))
    else:
        held = grouped_split(people, key, rng) if people and not args.all_data else set()
    train_groups = {p[key] for p in people if p[key] not in held}
    held_paths = (per_label_holdout([r for r in records if 'tensor' in r], one_per_day=one_per_day)
                  if split_per_label else set())
    for r in records:
        if 'tensor' not in r:
            r['split'] = 'excluded'
        elif split_per_label:
            if r['label']:
                r['split'] = 'test' if r['path'] in held_paths else 'train'
            else:
                r['split'] = 'control_test' if r['path'] in held_paths else 'control_reference'
        elif r['label']:
            r['split'] = 'test' if r[key] in held else 'train'
        else:
            r['split'] = 'control_heldout' if r[key] not in train_groups else 'control_same_group'
    if split_per_label:
        enrollment_sessions = {r['session'] for r in records if r['split'] in ('train', 'control_reference')}
        for r in records:
            if r['split'] in ('test', 'control_test'):
                r['session_in_train'] = r['session'] in enrollment_sessions
    run = output_base / (datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:6])
    run.mkdir(parents=True, exist_ok=False)
    dump(run / 'manifest.json', [{k: v for k, v in r.items() if k != 'tensor'} for r in records])
    report = dict(source=str(source), qc=dict(Counter(r['qc'] for r in records)), group_by=key,
                  mode=('per_label_day_holdout' if one_per_day else 'per_label_holdout' if split_per_label else
                        'full_fit' if args.all_data else 'fixed_holdout' if test_days else 'grouped_holdout'),
                  architecture=args.arch, excluded_days=sorted(exclude_days),
                  baseline_warn=args.baseline_warn,
                  split=dict(Counter(r['split'] for r in records)),
                  train_groups=sorted({r[key] for r in people if r['split'] == 'train'}),
                  test_groups=sorted({r[key] for r in people if r['split'] == 'test'}),
                  train_by_label=dict(Counter(r['label'] for r in people if r['split'] == 'train')),
                  test_by_label=dict(Counter(r['label'] for r in people if r['split'] == 'test')))
    report['labels_without_holdout'] = sorted(set(labels) - set(report['test_by_label']))
    dump(run / 'report.json', report)
    print(f'Output: {run}', flush=True)
    print('QC: ' + ' | '.join(f'{status}: {count}' for status, count in sorted(report['qc'].items())),
          flush=True)
    if args.audit_only:
        return run
    if len(labels) < 2:
        raise ValueError('Cần ít nhất hai danh tính có mẫu đạt QC để train. Xem report.json.')

    import torch
    from torch.nn import functional as F
    from .model import ARCHITECTURES

    torch.manual_seed(args.seed)
    torch.set_num_threads(min(torch.get_num_threads(), 4))
    training = [r for r in people if r['split'] == 'train']
    tensor = np.stack([r['tensor'] for r in training])
    p25, center, p75 = np.percentile(tensor, [25, 50, 75], axis=(0, 2))
    spread = p75-p25
    scale = np.where(spread > 1e-8, spread, 1)

    def scaled(array):
        return torch.as_tensor((array-center[:, None])/scale[:, None], dtype=torch.float32)

    x = scaled(tensor)
    y = torch.tensor([labels.index(r['label']) for r in training])
    weights = torch.bincount(y).float().reciprocal()
    model = ARCHITECTURES[args.arch](len(labels))
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.0001)
    print(f'Train {args.arch} | {len(y)} lượt | {len(labels)} người | {args.epochs} epoch', flush=True)
    history = []
    started = perf_counter()
    for epoch in range(1, args.epochs + 1):
        model.train()
        batch_losses = []
        for batch in torch.randperm(len(y)).split(16):
            optimizer.zero_grad()
            loss = F.cross_entropy(model(x[batch]), y[batch], weight=weights)
            if not torch.isfinite(loss):
                raise ValueError(f'Loss không hữu hạn ở epoch {epoch}. Kiểm tra dữ liệu và scaler.')
            loss.backward()
            optimizer.step()
            batch_losses.append(loss.item())
        mean_loss = sum(batch_losses) / len(batch_losses)
        elapsed = perf_counter() - started
        eta = elapsed / epoch * (args.epochs - epoch)
        history.append(dict(epoch=epoch, loss=mean_loss, elapsed_seconds=round(elapsed, 2)))
        print(f'Epoch {epoch:3d}/{args.epochs} | loss {mean_loss:.4f} | '
              f'{elapsed:.1f}s đã chạy | còn khoảng {eta:.1f}s', flush=True)
    model.eval()
    with torch.inference_mode():
        vectors = model.encode(x)
        gallery = F.normalize(torch.stack([vectors[y == i].mean(0) for i in range(len(labels))]), dim=1)
        results = []
        for r in records:
            if r['split'] not in ('test', 'control_heldout', 'control_same_group', 'control_test'):
                continue
            vector = model.encode(scaled(r['tensor'][None]))
            similarity = (vector @ gallery.T).flatten().tolist()
            top = max(range(len(labels)), key=similarity.__getitem__)
            results.append(dict(path=r['path'], split=r['split'], label=r['label'], condition=r['condition'],
                                top_label=labels[top], cosine=similarity[top],
                                scores=dict(zip(labels, similarity))))
    dump(run / 'scores.json', results)
    dump(run / 'training_history.json', history)
    dump(run / 'embeddings.json', [
        dict(path=r['path'], label=r['label'], condition=r['condition'], embedding=vector)
        for r, vector in zip(training, vectors.tolist())
    ])
    tests = [r for r in results if r['split'] == 'test']
    report.update(heldout_top1=sum(r['top_label'] == r['label'] for r in tests)/len(tests) if tests else None,
                  epochs=args.epochs, seed=args.seed, threshold=None)
    dump(run / 'report.json', report)
    dump(run / 'model.json', dict(version=1, channels=[k for k, _ in SIGNALS], labels=labels,
                                 architecture=args.arch, baseline_warn=args.baseline_warn,
                                 center=center.tolist(), scale=scale.tolist()))
    torch.save(dict(weights=model.state_dict(), gallery=gallery), run / 'model.pt')
    print(f'Train: {len(training)} | embedding: {vectors.shape[1]}D | held-out: {len(tests)} | top-1: {report["heldout_top1"]}', flush=True)
    print(f'Đã lưu model: {run / "model.pt"}', flush=True)
    print(f'Đã lưu embedding từng lượt: {run / "embeddings.json"}', flush=True)
    return run


def load_encoder(path):
    import torch
    from .model import ARCHITECTURES

    settings = json.loads((path / 'model.json').read_text(encoding='utf-8'))
    if settings.get('version') != 1 or settings['channels'] != [k for k, _ in SIGNALS]:
        raise ValueError('Model không tương thích với pipeline hiện tại.')
    labels = settings['labels']
    checkpoint = torch.load(path / 'model.pt', map_location='cpu', weights_only=True)
    model = ARCHITECTURES[settings.get('architecture', 'simple16')](len(labels))
    model.load_state_dict(checkpoint['weights'])
    model.eval()
    return model, settings, checkpoint['gallery']


def embed_sample(model, settings, sample):
    import torch

    record = {}
    x = prepare(sample, record, baseline_warn=settings.get('baseline_warn', False))
    x = (x - np.asarray(settings['center'])[:, None]) / np.asarray(settings['scale'])[:, None]
    with torch.inference_mode():
        vector = model.encode(torch.tensor(x[None], dtype=torch.float32))
    return vector, record.get('warnings', [])


def predict(args):
    import torch

    model, settings, gallery = load_encoder(args.model)
    labels = settings['labels']
    vector, warnings = embed_sample(model, settings, args.sample)
    with torch.inference_mode():
        scores = (vector @ gallery.T).flatten().tolist()
    best = max(range(len(labels)), key=scores.__getitem__)
    verdict = None if args.threshold is None else labels[best] if scores[best] >= args.threshold else 'unknown'
    print(json.dumps(dict(top_label=labels[best], cosine=scores[best], verdict=verdict,
                          scores=dict(zip(labels, scores)), embedding=vector[0].tolist(),
                          warnings=warnings), ensure_ascii=True, indent=2))


def compare(args):
    import torch

    model, settings, _ = load_encoder(args.model)
    a, a_warnings = embed_sample(model, settings, args.sample_a)
    b, b_warnings = embed_sample(model, settings, args.sample_b)
    with torch.inference_mode():
        score = (a @ b.T).clamp(-1, 1).item()
    print(json.dumps(dict(cosine=score, embedding_dims=a.shape[1],
                          warnings_a=a_warnings, warnings_b=b_warnings), ensure_ascii=True, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    fit = commands.add_parser('train')
    fit.add_argument('--data', type=Path, default=ROOT / 'curated_raw')
    fit.add_argument('--audit-only', action='store_true')
    fit.add_argument('--all-data', action='store_true', help='Train trên mọi lượt người qua QC, không giữ test.')
    fit.add_argument('--baseline-warn', action='store_true', help='Giữ lượt hợp lệ có nền trôi và ghi cảnh báo.')
    fit.add_argument('--arch', choices=('simple16', 'rescnn64'), default='simple16')
    fit.add_argument('--group-by', choices=('day', 'session'), default='day')
    fit.add_argument('--test-day', dest='test_days', action='append', default=[], help='Ngày test cố định YYYY-MM-DD.')
    fit.add_argument('--per-label', action='store_true', help='Giữ riêng 10–20% từng nhãn, ít nhất một lượt nếu có thể.')
    fit.add_argument('--per-label-day', action='store_true', help='Chừa một lượt cho mỗi nhãn và ngày, giữ ít nhất một mẫu gốc mỗi nhãn.')
    fit.add_argument('--exclude-day', dest='exclude_days', action='append', default=[], help='Bỏ ngày YYYY-MM-DD khỏi cả train và test.')
    fit.add_argument('--seed', type=int, default=42)
    fit.add_argument('--epochs', type=int, default=40)
    infer = commands.add_parser('predict')
    infer.add_argument('--model', type=Path, required=True)
    infer.add_argument('--sample', type=Path, required=True)
    infer.add_argument('--threshold', type=float)
    pair = commands.add_parser('compare')
    pair.add_argument('--model', type=Path, required=True)
    pair.add_argument('--sample-a', type=Path, required=True)
    pair.add_argument('--sample-b', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'train' and args.epochs < 1:
        parser.error('--epochs phải từ 1 trở lên.')
    if args.command == 'predict' and args.threshold is not None and not -1 <= args.threshold <= 1:
        parser.error('--threshold phải nằm trong [-1, 1].')
    try:
        {'train': train, 'predict': predict, 'compare': compare}[args.command](args)
    except (ValueError, OSError, ImportError, KeyError, csv.Error) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()

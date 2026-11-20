"""Score every unordered pair of usable recordings for a saved encoder."""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import csv
from itertools import combinations
import json
from pathlib import Path
from uuid import uuid4

import numpy as np

from .preprocess import prepare
from .run import RUNS, dump, load_encoder


def describe(scores):
    if not scores:
        return {'pairs': 0}
    low, median, high = np.percentile(scores, [10, 50, 90])
    return dict(pairs=len(scores), minimum=min(scores), p10=float(low),
                median=float(median), p90=float(high), maximum=max(scores))


def auc(positives, negatives):
    """Probability that a random same-person score beats a different-person score."""
    if not positives or not negatives:
        return None
    ordered = sorted(negatives)
    wins = sum((bisect_left(ordered, score) + bisect_right(ordered, score)) / 2
               for score in positives)
    return wins / (len(positives) * len(negatives))


def write_recognition_tables(output, rows, embeddings, labels, *, include_controls=False, full_fit=False):
    """Rank each probe against normalized means of train embeddings."""
    control_labels = {'cf': 'CF', 'kk_baseline': 'kk_baseline'}
    if include_controls:
        labels = [*labels, *control_labels.values()]

    def actual_label(row):
        if row['label'] or not include_controls:
            return row['label']
        return control_labels.get(row['condition'])

    indices = {label: i for i, label in enumerate(labels)}
    sums = np.zeros((len(labels), embeddings.shape[1]), dtype=np.float64)
    counts = np.zeros(len(labels), dtype=int)
    for row, vector in zip(rows, embeddings):
        if row['split'] == 'train' or (include_controls and (
                row['split'] in ('control_reference', 'control_same_group')
                or full_fit and row['split'] == 'control_heldout')):
            index = indices[actual_label(row)]
            sums[index] += vector
            counts[index] += 1

    if include_controls:
        gallery = {}
        for label, index in indices.items():
            norm = np.linalg.norm(sums[index])
            if counts[index] and norm > 1e-12:
                gallery[label] = dict(count=int(counts[index]), embedding=(sums[index]/norm).tolist())
        dump(output / 'reference_embeddings.json', gallery)

    predictions = []
    totals = defaultdict(Counter)
    sessions = defaultdict(Counter)
    for row, vector in zip(rows, embeddings):
        actual = actual_label(row)
        gallery = sums.copy()
        sizes = counts.copy()
        if row['split'] == 'train' and not include_controls:
            index = indices[row['label']]
            gallery[index] -= vector
            sizes[index] -= 1
        norms = np.linalg.norm(gallery, axis=1)
        valid = (sizes > 0) & (norms > 1e-12)
        scores = np.full(len(labels), -np.inf)
        scores[valid] = np.clip((gallery[valid] @ vector) / norms[valid], -1, 1)
        ranked = sorted(np.flatnonzero(valid), key=lambda i: scores[i], reverse=True)
        best = ranked[0] if ranked else None
        runner = ranked[1] if len(ranked) > 1 else None
        prediction = labels[best] if best is not None else None
        if not actual:
            result = 'control'
        elif not valid[indices[actual]]:
            result = 'no_reference'
        else:
            result = 'correct' if prediction == actual else 'incorrect'
        totals[row['split']][result] += 1
        sessions[row['day'], row['session'], row['split']][result] += 1
        predictions.append(dict(path=row['path'], day=row['day'], session=row['session'],
                                split=row['split'], condition=row['condition'], actual=actual,
                                predicted=prediction, result=result,
                                cosine=float(scores[best]) if best is not None else None,
                                reference_count=int(sizes[best]) if best is not None else 0,
                                runner_up=labels[runner] if runner is not None else None,
                                runner_up_cosine=float(scores[runner]) if runner is not None else None))

    def stats(counter):
        correct, incorrect = counter['correct'], counter['incorrect']
        scored = correct + incorrect
        return dict(total=sum(counter.values()), correct=correct, incorrect=incorrect,
                    no_reference=counter['no_reference'], controls=counter['control'],
                    accuracy=correct/scored if scored else None)

    session_rows = [dict(day=day, session=session, split=split, **stats(counter))
                    for (day, session, split), counter in sorted(sessions.items())]
    suffix = '_all_labels' if include_controls else ''
    for name, items in [(f'recognition{suffix}.csv', predictions),
                        (f'recognition_by_session{suffix}.csv', session_rows)]:
        with (output / name).open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(items[0]))
            writer.writeheader()
            writer.writerows(items)
    return {split: stats(counter) for split, counter in sorted(totals.items())}


def evaluate_all(model_dir):
    import torch

    model_dir = Path(model_dir).resolve(strict=True)
    report = json.loads((model_dir / 'report.json').read_text(encoding='utf-8'))
    manifest = json.loads((model_dir / 'manifest.json').read_text(encoding='utf-8'))
    source = Path(report['source']).resolve(strict=True)
    output_base = RUNS.resolve()
    if output_base != RUNS or source == output_base or source in output_base.parents or output_base in source.parents:
        raise ValueError('Nguồn và thư mục báo cáo phải nằm ở hai cây riêng.')
    model, settings, _ = load_encoder(model_dir)
    torch.set_num_threads(min(torch.get_num_threads(), 4))

    rows, tensors, skipped = [], [], []
    for row in manifest:
        if row['split'] == 'excluded':
            skipped.append(dict(path=row['path'], reason=row.get('reason', 'Bị loại khi kiểm QC.')))
            continue
        info = {'condition': row['condition']}
        try:
            tensor = prepare(source / row['path'], info, baseline_warn=settings.get('baseline_warn', False))
            if any(info.get(key) != row.get(key) for key in ('sha256', 'trial_id', 'day', 'session', 'config_hash')):
                raise ValueError('Dữ liệu hoặc thông tin lượt đã đổi từ lúc train.')
        except (ValueError, TypeError, OSError, KeyError, csv.Error) as exc:
            skipped.append(dict(path=row['path'], reason=str(exc)))
            continue
        rows.append(row)
        tensors.append(tensor)
    if len(rows) < 2:
        raise ValueError('Cần ít nhất hai lượt còn hợp lệ để so cặp.')

    center = np.asarray(settings['center'])[:, None]
    scale = np.asarray(settings['scale'])[:, None]
    inputs = torch.as_tensor((np.stack(tensors)-center)/scale, dtype=torch.float32)
    with torch.inference_mode():
        embeddings = torch.cat([model.encode(batch) for batch in inputs.split(32)])
        similarities = (embeddings @ embeddings.T).clamp(-1, 1).numpy()

    output = output_base / f'pair_eval_{model_dir.name}_{uuid4().hex[:6]}'
    output.mkdir(parents=True, exist_ok=False)
    recognition = write_recognition_tables(output, rows, embeddings.numpy(), settings['labels'])
    all_labels = write_recognition_tables(output, rows, embeddings.numpy(), settings['labels'],
                                          include_controls=True, full_fit=report.get('mode') == 'full_fit')
    slices = defaultdict(lambda: defaultdict(list))
    pairs = 0
    with (output / 'pairs.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['path_a', 'path_b', 'label_a', 'label_b', 'condition_a', 'condition_b',
                         'session_a', 'session_b', 'day_a', 'day_b', 'split_a', 'split_b', 'pair_type', 'cosine'])
        for (i, a), (j, b) in combinations(enumerate(rows), 2):
            if a['label'] and b['label']:
                kind = 'same_person' if a['label'] == b['label'] else 'different_person'
            elif a['label'] or b['label']:
                control = b if a['label'] else a
                kind = 'person_vs_' + control['condition']
            else:
                kind = 'control_vs_control'
            score = float(similarities[i, j])
            relation = 'same_session' if a['session'] == b['session'] else 'different_session'
            selections = ['all', relation]
            if a['day'] != b['day']:
                selections.append('different_day')
            if a['split'] == b['split'] == 'test':
                selections.append('holdout_only')
                if a['session'] != b['session']:
                    selections.append('holdout_different_session')
            if kind == 'same_person' and a['condition'] != b['condition']:
                selections.append('same_person_different_condition')
            for selection in selections:
                slices[selection][kind].append(score)
            writer.writerow([a['path'], b['path'], a['label'], b['label'], a['condition'], b['condition'],
                             a['session'], b['session'], a['day'], b['day'], a['split'], b['split'], kind, score])
            pairs += 1

    statistics = {}
    for selection, categories in slices.items():
        statistics[selection] = {
            'categories': {kind: describe(scores) for kind, scores in categories.items()},
            'pair_auc': auc(categories.get('same_person'), categories.get('different_person')),
        }
    summary = dict(model=str(model_dir), mode=report.get('mode'), recordings=len(rows),
                   pairs=pairs, by_split=dict(Counter(row['split'] for row in rows)),
                   skipped=skipped, slices=statistics, recognition=recognition, recognition_all_labels=all_labels)
    dump(output / 'summary.json', summary)
    print(f'{len(rows)} lượt | {pairs} cặp | bỏ qua {len(skipped)} lượt')
    for name, view in statistics.items():
        print(name)
        for kind, values in view['categories'].items():
            print(f'  {kind}: {values["pairs"]} cặp, median cosine {values["median"]:+.3f}')
        if view['pair_auc'] is not None:
            print(f'  Pair AUC: {view["pair_auc"]:.3f}')
    if 'holdout_only' not in statistics:
        print('Không có cặp holdout. Điểm trên các mẫu đã train chỉ dùng để mô tả model.')
    print('Nhận diện theo mẫu gốc (train bỏ chính lượt đang thử):')
    for split, details in recognition.items():
        if details['accuracy'] is not None:
            scored = details['correct'] + details['incorrect']
            print(f'  {split}: {details["correct"]}/{scored} đúng ({details["accuracy"]:.1%})')
    print(f'Bảng từng lượt: {output / "recognition.csv"}')
    print(f'Bảng theo phiên: {output / "recognition_by_session.csv"}')
    print(f'Bảng mẫu gốc có cả CF/kk_baseline: {output / "recognition_all_labels.csv"}')
    print(f'Báo cáo: {output}')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    evaluate_all(parser.parse_args().model)

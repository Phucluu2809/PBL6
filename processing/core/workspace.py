"""Manual review registry and verified COPY-only operations outside the source tree."""
from __future__ import annotations

import csv
import getpass
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .signals import digest, inspect, read_json

DECISIONS = {'UNREVIEWED', 'KEEP', 'REVIEW', 'REJECT'}
SKIP_DIRS = {'.git', '.venv', 'myenv', '__pycache__', 'node_modules', 'PREPROCESSED'}


def now():
    return datetime.now(timezone.utc).isoformat()


def linked(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def within(path, root):
    return path == root or root in path.parents


def safe_name(name):
    name = str(name).strip()
    if not name or name in ('.', '..') or name.casefold() == '_robonose' or len(name) > 100 or name.endswith(('.', ' ')) or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise ValueError('Tên thư mục không hợp lệ. Không dùng dấu /, \\, :, ký tự điều khiển hoặc tên quá dài.')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError('Tên này được Windows dành riêng.')
    return name


def atomic_json(path, value):
    if path.parent.resolve() != path.parent.absolute():
        raise ValueError('Không ghi registry qua thư mục link/junction.')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and linked(path):
        raise ValueError('Không ghi registry qua link/junction.')
    # Only application-owned registry files are atomically replaced; never source files.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.review-', suffix='.tmp', delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


class Workspace:
    def __init__(self, storage_root):
        self.storage = Path(storage_root).resolve()
        self.lock = threading.RLock()
        self.source = self.target = None
        self.samples = {}
        self.data = {}
        self.scan_warnings = []
        self.details = {}
        self.last_source = (read_json(self.storage / 'last.json') or {}).get('source', '')

    def _assert_separate(self, source, target):
        if source.resolve() != source or target.resolve() != target:
            raise ValueError('Nguồn/đích đã đổi đường dẫn thực. Hãy chọn lại thư mục.')
        if within(target, source) or within(source, target):
            raise ValueError('Nguồn và đích phải là hai cây thư mục riêng, không trùng hoặc lồng nhau.')
        if within(target, self.storage) or within(self.storage, target):
            raise ValueError('Không dùng thư mục registry reviews/ hoặc thư mục bao phủ nó làm đích.')

    def _source_file(self, path):
        if linked(path) or not within(path.resolve(), self.source):
            raise ValueError('Không đọc file qua link/junction hoặc ngoài nguồn đã chọn.')
        return path

    def _save(self):
        if self.source is None:
            return
        if self.storage.resolve() != self.storage or within(self.storage.resolve(), self.source.resolve()):
            raise ValueError('Registry không được nằm trong cây nguồn.')
        self.data.update(source=str(self.source), target=str(self.target) if self.target else None, updated_at=now())
        atomic_json(self.storage / 'sessions' / f'{self.data["id"]}.json', self.data)
        atomic_json(self.storage / 'last.json', {'source': str(self.source)})

    def load_source(self, value):
        with self.lock:
            source = Path(str(value).strip().strip('"')).expanduser().resolve(strict=True)
            if not source.is_dir():
                raise ValueError('Nguồn phải là thư mục.')
            if within(self.storage, source) or within(source, self.storage):
                raise ValueError('Chọn thư mục data/ hoặc lượt thu, không chọn cây chứa registry của ứng dụng.')
            identifier = hashlib.sha256(os.path.normcase(str(source)).encode()).hexdigest()[:24]
            saved_path = self.storage / 'sessions' / f'{identifier}.json'
            saved = read_json(saved_path)
            if saved_path.exists() and not (saved and saved.get('version') == 1 and saved.get('source') == str(source)
                    and isinstance(saved.get('records'), dict) and isinstance(saved.get('history'), list) and isinstance(saved.get('copies'), list)):
                raise ValueError(f'Registry cũ không hợp lệ; không tự ghi đè: {saved_path}')
            self.source, self.target, self.details = source, None, {}
            self.data = saved if saved and saved.get('version') == 1 and saved.get('source') == str(source) else dict(version=1, id=identifier, records={}, history=[], copies=[])
            if self.data.get('target'):
                try:
                    target = Path(self.data['target']).resolve(strict=True)
                    self._assert_separate(source, target)
                    if target.is_dir():
                        self.target = target
                except (OSError, ValueError):
                    pass
            self._scan()
            self.last_source = str(source)
            self._save()
            return self.state()

    def _scan(self):
        self.samples, self.scan_warnings = {}, []

        def walk(folder):
            try:
                entries = sorted(folder.iterdir())
            except OSError as exc:
                self.scan_warnings.append(f'{folder.name}: {exc}')
                return
            raw = next((p for p in entries if p.name == 'raw.csv'), None)
            if raw is not None:
                try:
                    self._source_file(raw)
                    meta_path = folder / 'metadata.json'
                    metadata = read_json(self._source_file(meta_path)) if meta_path.exists() else None
                    metadata = metadata or {}
                    relative = raw.relative_to(self.source).as_posix()
                    key = hashlib.sha256(relative.encode()).hexdigest()[:24]
                    info = raw.stat()
                    self.samples[key] = dict(id=key, name=metadata.get('name') or metadata.get('original_name') or folder.name,
                        path=relative, folder=str(folder), size=info.st_size, modified=info.st_mtime_ns,
                        schema=metadata.get('schema', metadata.get('schema_version', 'UNKNOWN')),
                        status=metadata.get('status', 'UNKNOWN'), date=metadata.get('started_at', ''),
                        is_container=folder.name == 'session' or metadata.get('kind') == 'session')
                except (OSError, ValueError) as exc:
                    self.scan_warnings.append(f'{raw.relative_to(self.source)}: {exc}')
            for entry in entries:
                try:
                    if linked(entry):
                        self.scan_warnings.append(f'Bỏ qua link/junction: {entry.relative_to(self.source)}')
                    elif entry.is_dir() and entry.name not in SKIP_DIRS and not entry.name.startswith('.'):
                        walk(entry)
                except OSError as exc:
                    self.scan_warnings.append(f'{entry.name}: {exc}')
        walk(self.source)
        self.samples = dict(sorted(self.samples.items(), key=lambda pair: (str(pair[1]['date']), str(pair[1]['name'])), reverse=True))

    def refresh(self):
        with self.lock:
            if self.source:
                self._scan()
                self.details.clear()
            return self.state()

    def set_target(self, value):
        with self.lock:
            if not self.source:
                raise ValueError('Chọn thư mục nguồn trước.')
            target = Path(str(value).strip().strip('"')).expanduser().resolve()
            self._assert_separate(self.source, target)
            target.mkdir(parents=True, exist_ok=True)
            self.target = target.resolve(strict=True)
            self._assert_separate(self.source, self.target)
            self._save()
            return self.state()

    def groups(self):
        if not self.target:
            return []
        result = []
        for folder in sorted(self.target.iterdir()):
            if folder.name.startswith('.') or folder.name.casefold() == '_robonose':
                continue
            if folder.is_dir() and not linked(folder):
                try:
                    safe_name(folder.name)
                    result.append(folder.name)
                except ValueError:
                    pass
        return result

    def add_group(self, name):
        with self.lock:
            if not self.target:
                raise ValueError('Chọn thư mục đích trước.')
            self._assert_separate(self.source, self.target)
            name = safe_name(name)
            existing = next((g for g in self.groups() if g.casefold() == name.casefold()), None)
            if existing:
                return self.state()
            folder = self.target / name
            folder.mkdir(exist_ok=False)
            self._save()
            return self.state()

    def detail(self, key):
        with self.lock:
            sample = self.samples.get(key)
            if not sample:
                raise ValueError('Mẫu không có trong danh sách nguồn hiện tại.')
            raw = self._source_file(Path(sample['folder']) / 'raw.csv')
            meta = Path(sample['folder']) / 'metadata.json'
            if meta.exists():
                self._source_file(meta)
            signature = (raw.stat().st_size, raw.stat().st_mtime_ns, meta.stat().st_mtime_ns if meta.exists() else None)
            cached = self.details.get(key)
            if cached and cached[0] == signature:
                data = cached[1]
            else:
                data = inspect(raw, meta)
                data.update(id=key, name=sample['name'], source_path=sample['path'])
            record = self.data.get('records', {}).get(key)
            data['record_stale'] = bool(record and (record.get('raw_hash') != data['raw_hash'] or record.get('metadata_hash') != data['metadata_hash']))
            data['label_stale'] = bool(record and record.get('label') and (
                record.get('label_raw_hash', record.get('raw_hash')) != data['raw_hash'] or
                record.get('label_metadata_hash', record.get('metadata_hash')) != data['metadata_hash']))
            self.details[key] = (signature, data)
            if len(self.details) > 12:
                self.details.pop(next(iter(self.details)))
            return data

    def _verify_fingerprint(self, key, raw_hash, metadata_hash):
        sample = self.samples.get(key)
        if not sample:
            raise ValueError('Không có mẫu này trong nguồn.')
        folder = Path(sample['folder'])
        current_raw = digest(self._source_file(folder / 'raw.csv'))
        meta = folder / 'metadata.json'
        current_meta = digest(self._source_file(meta)) if meta.exists() else None
        if current_raw != raw_hash or current_meta != metadata_hash:
            self.details.pop(key, None)
            raise ValueError('SOURCE_CHANGED: mẫu thay đổi từ lúc xem. Đọc lại mẫu trước khi duyệt/copy.')

    def review(self, key, decision, note, raw_hash, metadata_hash):
        with self.lock:
            if decision not in DECISIONS:
                raise ValueError('Trạng thái duyệt không hợp lệ.')
            note = str(note).strip()
            if decision in {'REVIEW', 'REJECT'} and not note:
                raise ValueError('Nhập lý do cho Cần xem lại hoặc Loại.')
            self._verify_fingerprint(key, raw_hash, metadata_hash)
            previous = self.data['records'].get(key, {})
            record = dict(previous, decision=decision, note=note, raw_hash=raw_hash, metadata_hash=metadata_hash,
                          reviewed_at=now(), reviewed_by=getpass.getuser())
            self.data['records'][key] = record
            self.data['history'].append(dict(sample_id=key, event='review', record=dict(record), time=now()))
            self._save()
            return self.state()

    def _tree(self, folder, base=None):
        base = base or folder
        files, directories = [], []
        for entry in sorted(folder.iterdir()):
            if linked(entry) or not within(entry.resolve(), base.resolve()):
                raise ValueError(f'Không sao chép link/junction: {entry.name}')
            relative = entry.relative_to(base).as_posix()
            if entry.is_dir():
                directories.append(relative)
                children, dirs = self._tree(entry, base)
                files.extend(children)
                directories.extend(dirs)
            elif entry.is_file():
                files.append(dict(path=relative, size=entry.stat().st_size, sha256=digest(entry)))
            else:
                raise ValueError(f'Loại file chưa hỗ trợ: {entry.name}')
        return files, directories

    def copy(self, key, group, raw_hash, metadata_hash):
        with self.lock:
            if not self.target:
                raise ValueError('Chọn đích trước khi kéo thả.')
            self._assert_separate(self.source, self.target)
            self._verify_fingerprint(key, raw_hash, metadata_hash)
            group = safe_name(group)
            actual = next((g for g in self.groups() if g.casefold() == group.casefold()), None)
            if not actual:
                raise ValueError('Tạo/chọn thư mục người trước khi sao chép.')
            parent = self.target / actual
            if linked(parent) or not within(parent.resolve(), self.target):
                raise ValueError('Thư mục người không nằm trong đích được chọn.')
            source = Path(self.samples[key]['folder'])
            files, directories = self._tree(source)
            for receipt in self.data['copies']:
                if receipt.get('status') == 'complete' and receipt.get('sample_id') == key and receipt.get('target') == str(self.target) and receipt.get('group') == actual and receipt.get('files') == files:
                    destination = parent / receipt['folder']
                    try:
                        if linked(destination):
                            raise ValueError('Destination is linked')
                        copied, copied_dirs = self._tree(destination)
                        if copied == files and copied_dirs == directories:
                            # Relabeling to an already copied group is a new manual label decision.
                            self._label(key, actual, raw_hash, metadata_hash, receipt['id'])
                            self._save()
                            return dict(state=self.state(), receipt=receipt, duplicate=True)
                    except (OSError, ValueError):
                        pass
            name = source.name
            destination = parent / name
            for index in range(20):
                try:
                    destination.mkdir(exist_ok=False)
                    break
                except FileExistsError:
                    destination = parent / f'{source.name}__{key[:8]}_{uuid.uuid4().hex[:6]}'
            else:
                raise ValueError('Không tạo được thư mục bản sao duy nhất.')
            receipt = dict(id=uuid.uuid4().hex, sample_id=key, source_path=self.samples[key]['path'],
                           source_name=source.name, group=actual, folder=destination.name,
                           target=str(self.target), raw_hash=raw_hash, files=files, directories=directories,
                           time=now(), status='incomplete')
            self.data['copies'].append(receipt)
            try:
                for directory in directories:
                    (destination / directory).mkdir(parents=True, exist_ok=True)
                for entry in files:
                    src = self._source_file(source / entry['path'])
                    dst = destination / entry['path']
                    with src.open('rb') as reader, dst.open('xb') as writer:
                        shutil.copyfileobj(reader, writer, 1024 * 1024)
                        writer.flush()
                        os.fsync(writer.fileno())
                    if digest(dst) != entry['sha256']:
                        raise ValueError(f'Bản sao không khớp SHA-256: {entry["path"]}')
                after, after_dirs = self._tree(source)
                if after != files or after_dirs != directories:
                    raise ValueError('SOURCE_CHANGED: nguồn thay đổi trong khi sao chép.')
                receipt['status'] = 'complete'
                receipt['verified_at'] = now()
                self._label(key, actual, raw_hash, metadata_hash, receipt['id'])
                self._save()
                registry = self.target / '_robonose'
                if registry.exists() and linked(registry):
                    raise ValueError('Không ghi provenance qua link/junction.')
                registry.mkdir(exist_ok=True)
                # Sidecar outside copied folders; original metadata copies stay byte-identical.
                with (registry / f'copy_{receipt["id"]}.json').open('x', encoding='utf-8') as handle:
                    json.dump(receipt, handle, ensure_ascii=False, indent=2, allow_nan=False)
            except Exception as exc:
                if receipt['status'] == 'complete':
                    receipt['registry_warning'] = str(exc)
                    # Files are verified; communicate registry failure rather than silently re-copy.
                    try:
                        self._save()
                    except OSError:
                        pass
                    return dict(state=self.state(), receipt=receipt, duplicate=False, warning=f'File đã copy và kiểm hash; chưa lưu đủ provenance: {exc}')
                receipt['error'] = str(exc)
                self._save()
                raise ValueError(f'Copy chưa hoàn tất; giữ bản dở tại {destination}. Nguồn không bị sửa. {exc}') from exc
            return dict(state=self.state(), receipt=receipt, duplicate=False)

    def _label(self, key, group, raw_hash, metadata_hash, receipt_id):
        previous = self.data['records'].get(key, {})
        if previous and (previous.get('raw_hash') != raw_hash or previous.get('metadata_hash') != metadata_hash):
            previous = dict(previous, decision='UNREVIEWED', note='')
        record = dict(previous, label=group, raw_hash=raw_hash, metadata_hash=metadata_hash,
                      label_raw_hash=raw_hash, label_metadata_hash=metadata_hash,
                      labeled_at=now(), labeled_by=getpass.getuser(), receipt_id=receipt_id)
        self.data['records'][key] = record
        self.data['history'].append(dict(sample_id=key, event='label', label=group, receipt_id=receipt_id, time=now()))

    def state(self):
        with self.lock:
            return dict(source=str(self.source) if self.source else None, target=str(self.target) if self.target else None,
                last_source=self.last_source, samples=list(self.samples.values()), groups=self.groups(),
                records=self.data.get('records', {}), copies=self.data.get('copies', []),
                history=self.data.get('history', []), warnings=self.scan_warnings)

    def export_manifest(self):
        with self.lock:
            out = io.StringIO(newline='')
            columns = ['sample_id', 'source_path', 'raw_sha256', 'decision', 'note', 'label', 'copied_folder', 'verified_copy', 'review_current', 'label_current', 'reviewed_at']
            writer = csv.DictWriter(out, fieldnames=columns)
            writer.writeheader()
            for key, record in self.data.get('records', {}).items():
                receipt = next((c for c in self.data['copies'] if c['id'] == record.get('receipt_id')), {})
                review_current = label_current = False
                try:
                    current = self.detail(key)
                    review_current = not current.get('record_stale')
                    label_current = bool(record.get('label')) and not current.get('label_stale')
                except (ValueError, OSError):
                    pass
                row = dict(sample_id=key, source_path=self.samples.get(key, {}).get('path', ''), raw_sha256=record.get('raw_hash', ''),
                    decision=record.get('decision', 'UNREVIEWED'), note=record.get('note', ''), label=record.get('label', ''),
                    copied_folder=str(Path(receipt['target']) / receipt['group'] / receipt['folder']) if receipt else '',
                    verified_copy=receipt.get('status') == 'complete', review_current=review_current,
                    label_current=label_current, reviewed_at=record.get('reviewed_at', ''))
                # Spreadsheet formula injection protection; raw source labels are untouched.
                row = {k: "'" + str(v) if str(v).startswith(('=', '+', '-', '@', '\t', '\r')) else v for k, v in row.items()}
                writer.writerow(row)
            return ('\ufeff' + out.getvalue()).encode('utf-8')

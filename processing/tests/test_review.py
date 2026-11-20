import csv
import io
import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from processing.app import create_server
from processing.core.plots import svg_chart
from processing.core.signals import digest, inspect
from processing.core.workspace import Workspace, safe_name

CHECKS = Path(__file__).resolve().parents[1] / '.checks'


class ReviewTests(unittest.TestCase):
    def setUp(self):
        CHECKS.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='review-test-', dir=CHECKS)
        self.root = Path(self.temp.name).resolve()
        self.assertEqual(self.root.parent, CHECKS.resolve())
        self.source = self.root / 'source'
        self.sample = self.source / 'Phien' / 'trials' / 'Mau_001'
        self.sample.mkdir(parents=True)
        self.raw = self.sample / 'raw.csv'
        self.raw.write_text(
            'schema,mono_s,seq,timestamp,boot_id,phase,segment_id,tgs2602_voltage_v,tgs2602_status,tgs2602_fresh,tgs2602_valid,gas_resistance_ohm,bme688_status,bme688_fresh,bme688_valid,gas_valid,heater_stable,new_data\n'
            'robonose.dataset.v1,10,1,2026-11-18T10:00:00+07:00,b1,BASELINE,1,0.50,OK,true,true,1000,OK,true,true,true,true,true\n'
            'robonose.dataset.v1,11,2,2026-11-18T10:00:01+07:00,b1,BASELINE,1,0.51,OK,true,true,1010,OK,true,true,true,true,true\n'
            'robonose.dataset.v1,12,3,2026-11-18T10:00:02+07:00,b1,BASELINE,1,0.52,OK,true,true,1020,OK,true,true,true,true,true\n'
            'robonose.dataset.v1,13,4,2026-11-18T10:00:03+07:00,b1,EXPOSURE,2,0.80,OK,true,false,1100,OK,true,true,false,true,true\n'
            'robonose.dataset.v1,17,8,2026-11-18T10:00:07+07:00,b1,EXPOSURE,2,,ERROR,false,false,1200,OK,true,true,true,true,true\n'
            'robonose.dataset.v1,18,9,2026-11-18T10:00:08+07:00,b1,RECOVERY,3,0,OK,true,true,1250,OK,true,true,true,true,true\n', encoding='utf-8')
        self.meta = self.sample / 'metadata.json'
        self.meta.write_text(json.dumps({'name': 'Mẫu <001>', 'schema': 'robonose.dataset.v1', 'status': 'COMPLETE', 'config': {'sampling_hz': 1}}), encoding='utf-8')
        (self.sample / 'notes.txt').write_text('Ghi chú gốc, không đổi.', encoding='utf-8')
        (self.sample / 'empty').mkdir()
        (self.sample / 'images').mkdir()
        (self.sample / 'images' / 'chart.bin').write_bytes(b'\x89raw-image\x00')
        self.storage = self.root / 'registry'
        self.target = self.root / 'output'
        self.ws = Workspace(self.storage)
        self.ws.load_source(self.source)
        self.key = next(iter(self.ws.samples))

    def tearDown(self):
        # Cleanup is confined to the explicitly created fixture, never repository data/.
        self.assertEqual(self.root.parent, CHECKS.resolve())
        self.assertTrue(self.root.name.startswith('review-test-'))
        self.temp.cleanup()

    def prepare_copy(self):
        self.ws.set_target(self.target)
        self.ws.add_group('Nguyễn Văn Tài')
        return self.ws.detail(self.key)

    def copy(self, data, group='Nguyễn Văn Tài'):
        return self.ws.copy(self.key, group, data['raw_hash'], data['metadata_hash'])

    def test_raw_values_and_flags_are_not_modified(self):
        before = digest(self.raw)
        data = inspect(self.raw, self.meta)
        self.assertEqual(data['row_count'], 6)
        self.assertEqual(data['points'][3]['values']['tgs2602_voltage_v'], .8)
        self.assertFalse(data['points'][3]['valid']['tgs2602_voltage_v'])
        self.assertIsNone(data['points'][4]['values']['tgs2602_voltage_v'])
        self.assertEqual(data['points'][5]['values']['tgs2602_voltage_v'], 0)
        self.assertEqual(data['sampling_rate'], 1)
        self.assertEqual(data['max_gap'], 4)
        self.assertEqual(data['missing_sequence'], 3)
        self.assertAlmostEqual(data['channels'][0]['baseline_slope'], .6)
        self.assertEqual(digest(self.raw), before)

    def test_legacy_and_unknown_validity(self):
        self.raw.write_text('elapsed_s,phase,mq135_voltage_v,mq135_status,mq135_fresh\n0,BASELINE,1,OK,True\n1,EXPOSURE,2,OK,True\n', encoding='utf-8')
        data = inspect(self.raw, self.meta)
        self.assertTrue(data['points'][0]['valid']['mq135_voltage_v'])
        self.raw.write_text('elapsed_s,phase,mq135_voltage_v\n0,BASELINE,1\n1,EXPOSURE,2\n', encoding='utf-8')
        self.assertIsNone(inspect(self.raw, self.meta)['points'][0]['valid']['mq135_voltage_v'])

    def test_time_reversal_is_reported_not_sorted(self):
        self.raw.write_text('elapsed_s,phase,mq3_voltage_v\n3,BASELINE,1\n2,BASELINE,2\n', encoding='utf-8')
        data = inspect(self.raw, self.meta)
        self.assertEqual(data['time_errors'], 1)
        self.assertEqual([p['t'] for p in data['points']], [0, -1])
        self.assertIsNone(data['channels'][0]['observed_coverage'])

    def test_session_container_is_separate(self):
        folder = self.source / 'Phien' / 'session'
        folder.mkdir()
        (folder / 'raw.csv').write_bytes(self.raw.read_bytes())
        result = self.ws.refresh()
        self.assertEqual(len(result['samples']), 2)
        self.assertEqual(sum(s['is_container'] for s in result['samples']), 1)

    def test_copy_whole_folder_and_duplicate_no_overwrite(self):
        data = self.prepare_copy()
        before, dirs = self.ws._tree(self.sample)
        result = self.copy(data)
        receipt = result['receipt']
        destination = self.target / receipt['group'] / receipt['folder']
        self.assertEqual(self.ws._tree(destination), (before, dirs))
        self.assertEqual(self.ws._tree(self.sample), (before, dirs))
        self.assertTrue((destination / 'empty').is_dir())
        self.assertEqual((destination / 'metadata.json').read_bytes(), self.meta.read_bytes())
        again = self.copy(data)
        self.assertTrue(again['duplicate'])
        self.assertEqual(len(self.ws.data['copies']), 1)
        self.assertEqual(len(list((self.target / receipt['group']).iterdir())), 1)
        self.assertEqual(self.ws.data['records'][self.key].get('decision', 'UNREVIEWED'), 'UNREVIEWED')

    def test_name_collision_preserves_foreign_folder(self):
        data = self.prepare_copy()
        occupied = self.target / 'Nguyễn Văn Tài' / self.sample.name
        occupied.mkdir()
        (occupied / 'do-not-touch.txt').write_text('original destination', encoding='utf-8')
        copied = self.copy(data)['receipt']
        self.assertNotEqual(copied['folder'], self.sample.name)
        self.assertEqual((occupied / 'do-not-touch.txt').read_text(), 'original destination')

    def test_source_target_and_registry_cannot_overlap(self):
        for target in [self.source, self.sample / 'new', self.root, self.storage, self.storage / 'sub']:
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.ws.set_target(target)

    def test_stale_input_blocks_copy_and_review(self):
        data = self.prepare_copy()
        self.raw.write_text(self.raw.read_text() + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
            self.copy(data)
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
            self.ws.review(self.key, 'KEEP', '', data['raw_hash'], data['metadata_hash'])
        self.assertEqual(list((self.target / 'Nguyễn Văn Tài').iterdir()), [])

    def test_copy_failure_remains_incomplete_and_keeps_source(self):
        data = self.prepare_copy()
        before = self.ws._tree(self.sample)
        with patch('processing.core.workspace.shutil.copyfileobj', side_effect=OSError('simulated disk error')):
            with self.assertRaisesRegex(ValueError, 'Copy chưa hoàn tất'):
                self.copy(data)
        self.assertEqual(self.ws.data['copies'][0]['status'], 'incomplete')
        self.assertNotIn(self.key, self.ws.data['records'])
        self.assertEqual(self.ws._tree(self.sample), before)

    def test_manual_review_and_label_are_independent_and_persist(self):
        data = self.prepare_copy()
        self.ws.review(self.key, 'REJECT', 'Nhiễu do thao tác', data['raw_hash'], data['metadata_hash'])
        self.copy(data)
        self.assertEqual(self.ws.data['records'][self.key]['decision'], 'REJECT')
        self.ws.add_group('Người B')
        self.copy(data, 'Người B')
        self.assertEqual(self.ws.data['records'][self.key]['label'], 'Người B')
        self.assertTrue((self.target / 'Nguyễn Văn Tài' / 'Mau_001').exists())
        restored = Workspace(self.storage)
        restored.load_source(self.source)
        self.assertEqual(restored.data['records'][self.key]['decision'], 'REJECT')
        self.assertEqual(restored.data['records'][self.key]['label'], 'Người B')
        self.assertGreaterEqual(len(restored.data['history']), 3)

    def test_review_requires_reason_and_valid_name(self):
        data = self.ws.detail(self.key)
        for decision in ('REJECT', 'REVIEW'):
            with self.assertRaises(ValueError):
                self.ws.review(self.key, decision, '', data['raw_hash'], data['metadata_hash'])
        for name in ('../escape', 'A/B', 'CON', 'NUL.txt', 'COM1', '_robonose', 'A?', '.'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_name(name)

    def test_label_stays_stale_when_only_qc_is_updated_after_source_change(self):
        data = self.prepare_copy()
        self.copy(data)
        self.raw.write_text(self.raw.read_text()+'\n', encoding='utf-8')
        fresh = self.ws.detail(self.key)
        self.assertTrue(fresh['label_stale'])
        self.ws.review(self.key, 'KEEP', '', fresh['raw_hash'], fresh['metadata_hash'])
        current = self.ws.detail(self.key)
        self.assertFalse(current['record_stale'])
        self.assertTrue(current['label_stale'])

    def test_changed_source_copy_does_not_reuse_old_keep_decision(self):
        data = self.prepare_copy()
        self.ws.review(self.key, 'KEEP', '', data['raw_hash'], data['metadata_hash'])
        self.copy(data)
        self.raw.write_text(self.raw.read_text()+'\n', encoding='utf-8')
        fresh = self.ws.detail(self.key)
        copied = self.copy(fresh)
        self.assertFalse(copied['duplicate'])
        self.assertEqual(self.ws.data['records'][self.key]['decision'], 'UNREVIEWED')

    def test_plot_is_valid_svg_and_escapes_title(self):
        data = self.ws.detail(self.key)
        svg = svg_chart(data, 'tgs2602_voltage_v', '<script>bad</script>')
        ElementTree.fromstring(svg)
        self.assertNotIn(b'<script>', svg)
        self.assertIn(b'&lt;script&gt;', svg)

    def test_export_escapes_spreadsheet_formula_and_flags_stale(self):
        data = self.ws.detail(self.key)
        self.ws.review(self.key, 'REVIEW', '=1+1', data['raw_hash'], data['metadata_hash'])
        self.raw.write_text(self.raw.read_text()+'\n', encoding='utf-8')
        rows = list(csv.DictReader(io.StringIO(self.ws.export_manifest().decode('utf-8-sig'))))
        self.assertEqual(rows[0]['note'], "'=1+1")
        self.assertEqual(rows[0]['review_current'], 'False')

    def test_public_mode_validates_configuration(self):
        for public_url, password in [('http://review.example', 'long-test-password'), ('https://review.example/path', 'long-test-password'), ('https://review.example', 'short')]:
            with self.subTest(public_url=public_url, password=password), self.assertRaises(ValueError):
                create_server(0, self.root / 'shared-registry', public_url=public_url, share_password=password)

    def test_public_mode_without_password(self):
        server = create_server(0, self.root / 'open-registry', public_url='https://review.example')
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            headers = {'Host': 'review.example'}
            html = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5).read().decode()
            token = re.search(r'name="review-token" content="([^"]+)"', html)[1]
            headers.update({'X-Review-Token': token, 'Origin': 'https://review.example', 'Content-Type': 'application/json'})
            req = urllib.request.Request(url+'/api/source', data=json.dumps({'path': str(self.source)}).encode(), headers=headers)
            self.assertTrue(json.loads(urllib.request.urlopen(req, timeout=5).read())['samples'])
            for extra in ({'Host': 'other.example'}, {'Origin': 'https://other.example'}, {'X-Review-Token': 'wrong'}):
                with self.subTest(extra=extra), self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url+'/api/state', headers={**headers, **extra}), timeout=5)
                self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_public_host_and_origin_require_login(self):
        import base64
        public = 'https://review.example'
        server = create_server(0, self.root / 'shared-registry', public_url=public, share_password='long-test-password')
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f'http://127.0.0.1:{server.server_port}'
        authorization = 'Basic '+base64.b64encode(b'reviewer:long-test-password').decode()
        try:
            for path in ('/', '/static/app.js', '/api/state'):
                with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url+path, headers={'Host': 'review.example'}), timeout=5)
                self.assertEqual(error.exception.code, 401)
                self.assertIn('Basic', error.exception.headers['WWW-Authenticate'])
            headers = {'Host': 'review.example', 'Authorization': authorization}
            html = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5).read().decode()
            token = re.search(r'name="review-token" content="([^"]+)"', html)[1]
            headers.update({'X-Review-Token': token, 'Content-Type': 'application/json', 'Origin': public})
            request = urllib.request.Request(url+'/api/source', data=json.dumps({'path': str(self.source)}).encode(), headers=headers)
            self.assertTrue(json.loads(urllib.request.urlopen(request, timeout=5).read())['samples'])
            for extra in ({'Origin': 'https://other.example'}, {'Host': 'other.example'}, {'Authorization': 'Basic broken'}):
                with self.subTest(extra=extra), self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url+'/api/state', headers={**headers, **extra}), timeout=5)
                self.assertIn(error.exception.code, (401, 403))
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_http_auth_ui_detail_copy_and_svg(self):
        server = create_server(0, self.root / 'http-registry')
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            html = urllib.request.urlopen(url, timeout=5).read().decode('utf-8')
            token = re.search(r'name="review-token" content="([^"]+)"', html)[1]

            def request(path, payload=None, **headers):
                data = json.dumps(payload).encode() if payload is not None else None
                req = urllib.request.Request(url+path, data=data, headers={'X-Review-Token': token, 'Content-Type': 'application/json', **headers})
                with urllib.request.urlopen(req, timeout=10) as response:
                    return response.read()

            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(url+'/api/state', timeout=5)
            self.assertEqual(denied.exception.code, 403)
            with self.assertRaises(urllib.error.HTTPError) as origin:
                request('/api/source', {'path': str(self.source)}, Origin='https://outside.example')
            self.assertEqual(origin.exception.code, 403)
            state = json.loads(request('/api/source', {'path': str(self.source)}))
            key = state['samples'][0]['id']
            detail = json.loads(request('/api/sample?id='+key))
            request('/api/target', {'path': str(self.target)})
            request('/api/groups', {'name': 'Người A'})
            result = json.loads(request('/api/copy', {'id': key, 'group': 'Người A', 'raw_hash': detail['raw_hash'], 'metadata_hash': detail['metadata_hash']}))
            self.assertEqual(result['receipt']['status'], 'complete')
            ElementTree.fromstring(request('/api/plot?id='+key+'&channel=tgs2602_voltage_v'))
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == '__main__':
    unittest.main()

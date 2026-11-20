/** Local, read-only dataset adapter. Never follows links or exposes arbitrary file paths. */
import { readdir, readFile, realpath, stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { createHash } from 'node:crypto';
import { resolve, relative, dirname, basename, sep, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';

const DEFAULT_ROOT = fileURLToPath(new URL('../../data/', import.meta.url));
const CHANNELS = [
  ['tgs2602_voltage_v', 'TGS2602', 'V', 'tgs2602'],
  ['mq135_voltage_v', 'MQ135', 'V', 'mq135'],
  ['mq3_voltage_v', 'MQ3', 'V', 'mq3'],
  ['mq135_1_voltage_v', 'MQ135 #1', 'V', 'mq135_1'],
  ['mq3_1_voltage_v', 'MQ3 #1', 'V', 'mq3_1'],
  ['mq135_2_voltage_v', 'MQ135 #2', 'V', 'mq135_2'],
  ['mq3_2_voltage_v', 'MQ3 #2', 'V', 'mq3_2'],
  ['gas_resistance_ohm', 'BME gas', 'Ω', 'bme'],
  ['temperature_c', 'Nhiệt độ', '°C', 'environment'],
  ['humidity_pct', 'Độ ẩm', '%RH', 'environment'],
  ['pressure_hpa', 'Áp suất', 'hPa', 'environment'],
];
export function parseCSVLine(line) {
  const cells = [];
  let value = '';
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') {
      if (quoted && line[i + 1] === '"') {
        value += '"';
        i++;
      } else quoted = !quoted;
    } else if (c === ',' && !quoted) {
      cells.push(value);
      value = '';
    } else value += c;
  }
  cells.push(value.replace(/\r$/, ''));
  return cells;
}
const number = (v) =>
  v !== undefined && String(v).trim() !== '' && Number.isFinite(Number(v)) ? Number(v) : null;
const falseFlag = (v) => /^(false|0|invalid)$/i.test(v ?? '');
function valid(row, key, sensor) {
  if (number(row[key]) === null) return false;
  if (sensor === 'environment') {
    const status = row.bme688_status || row.bme_status;
    return (
      (!status || status === 'OK') &&
      !falseFlag(row.bme688_valid) &&
      !falseFlag(row.bme688_fresh) &&
      !falseFlag(row.bme_fresh)
    );
  }
  if (sensor === 'bme') {
    const status = row.bme688_status || row.bme_status;
    return (
      (!status || status === 'OK') &&
      !['bme688_valid', 'bme688_fresh', 'bme_fresh', 'gas_valid', 'heater_stable', 'new_data'].some(
        (k) => falseFlag(row[k]),
      )
    );
  }
  return (
    (!row[sensor + '_status'] || row[sensor + '_status'] === 'OK') &&
    !falseFlag(row[sensor + '_valid']) &&
    !falseFlag(row[sensor + '_fresh']) &&
    !/NEGATIVE|ADC_LIMIT/.test(row[sensor + '_quality'] ?? '')
  );
}
export function identifyLabel(label) {
  const token = label
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .toLowerCase()
    .split(/[_\s]/)[0];
  if (['tai', 'atai', 'basetai', 'taivscf'].includes(token)) return 'P001';
  if (['duong', 'aduong', 'duongcaphe2'].includes(token)) return 'P002';
  if (['phuc', 'phucluu', 'luuhoangphuc', 'phucgg', 'phuuc'].includes(token)) return 'P003';
  return null;
}
export function createDatasetReader(root = DEFAULT_ROOT) {
  const absoluteRoot = resolve(root);
  const records = new Map();
  let scanPromise;
  let lastScan = 0;
  let catalog;
  async function confined(path) {
    const actual = await realpath(path);
    const base = await realpath(absoluteRoot);
    const rel = relative(base, actual);
    if (rel === '..' || rel.startsWith('..' + sep) || resolve(actual) === base || isAbsolute(rel))
      throw new Error('Path outside dataset');
    return actual;
  }
  async function json(path) {
    try {
      return JSON.parse((await readFile(await confined(path), 'utf8')).replace(/^\uFEFF/, ''));
    } catch {
      return null;
    }
  }
  async function* rows(path) {
    const stream = createReadStream(await confined(path), { encoding: 'utf8' });
    const lines = createInterface({ input: stream, crlfDelay: Infinity });
    let header;
    try {
      for await (const line of lines) {
        if (!header) {
          header = parseCSVLine(line.replace(/^\uFEFF/, ''));
          continue;
        }
        if (!line.trim()) continue;
        const cells = parseCSVLine(line);
        yield Object.fromEntries(header.map((k, i) => [k, cells[i] ?? '']));
      }
    } finally {
      lines.close();
      stream.destroy();
    }
  }
  async function walk(dir, found) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      if (entry.isSymbolicLink()) continue;
      const path = resolve(dir, entry.name);
      if (entry.isDirectory()) await walk(path, found);
      else if (entry.isFile() && entry.name === 'raw.csv') found.push(path);
    }
  }
  async function scan() {
    records.clear();
    const paths = [];
    const samples = [];
    const warnings = [];
    let skippedSessions = 0;
    try {
      await walk(absoluteRoot, paths);
    } catch (e) {
      if (e.code === 'ENOENT')
        return {
          samples: [],
          warnings: ['Không tìm thấy thư mục data/ cạnh frontend/.'],
          source: 'data/',
          readOnly: true,
          skippedSessions: 0,
        };
      throw e;
    }
    for (const path of paths) {
      const folder = dirname(path);
      const metadata = await json(resolve(folder, 'metadata.json'));
      const summary = await json(resolve(folder, 'summary.json'));
      // Session logs contain the same trials. Keep individual trial exports and avoid double counting.
      if (basename(folder) === 'session' || metadata?.kind === 'session') {
        skippedSessions++;
        continue;
      }
      try {
        let first = null,
          last = null,
          count = 0;
        const phases = new Set();
        const present = new Set();
        const stats = await stat(await confined(path));
        for await (const row of rows(path)) {
          first ??= row;
          last = row;
          count++;
          phases.add(row.phase);
          for (const [key] of CHANNELS) if (number(row[key]) !== null) present.add(key);
        }
        const rel = relative(absoluteRoot, path).split(sep).join('/');
        const id = 'DATA-' + createHash('sha256').update(rel).digest('hex').slice(0, 16);
        const name =
          metadata?.name ||
          metadata?.original_name ||
          basename(folder)
            .replace(/_\d{6}_\d{4}-\d{2}-\d{2}_.+$/, '')
            .replace(/_\d{8}_\d{6}_.+$/, '');
        const personId = identifyLabel(name);
        const person = personId ?? 'UNASSIGNED';
        const start = number(first?.mono_s) ?? number(first?.elapsed_s);
        const end = number(last?.mono_s) ?? number(last?.elapsed_s);
        const qcSource = String(summary?.quality ?? 'Chưa có kết luận QC');
        const qc = ['PASS', 'FAIL'].includes(qcSource)
          ? qcSource
          : qcSource === 'INSUFFICIENT' || metadata?.status === 'ERROR'
            ? 'FAIL'
            : 'REVIEW';
        const config = metadata?.config ?? {};
        samples.push({
          id,
          person,
          name,
          date: metadata?.started_at || first?.timestamp || '',
          qc,
          qcSource,
          duration:
            start !== null && end !== null
              ? Math.max(0, end - start)
              : Number(metadata?.elapsed_s) || 0,
          device: metadata?.schema ? 'ESP32-S3' : 'Legacy logger',
          protocol: [config.baseline_s, config.exposure_s, config.recovery_s].every(
            (v) => v !== undefined,
          )
            ? `${config.baseline_s} / ${config.exposure_s} / ${config.recovery_s} s`
            : 'Theo metadata gốc',
          note: metadata?.notes || '',
          readOnly: true,
          sourcePath: rel,
          rowCount: count,
          bytes: stats.size,
          phases: [...phases],
          channels: CHANNELS.filter(([key]) => present.has(key)).map(([key, label, unit]) => ({
            key,
            label,
            unit,
          })),
          schema: metadata?.schema || metadata?.schema_version || 'unknown',
          processStatus:
            metadata?.status || summary?.process_status || summary?.status || 'UNKNOWN',
        });
        records.set(id, { path, folder });
      } catch (e) {
        warnings.push(
          `${relative(absoluteRoot, path)}: không đọc được mẫu (${e.code ?? e.message}).`,
        );
      }
    }
    samples.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
    return {
      samples,
      warnings,
      source: 'data/',
      readOnly: true,
      skippedSessions,
      scannedAt: new Date().toISOString(),
    };
  }
  async function getCatalog(refresh = false) {
    if (scanPromise) return scanPromise;
    if (catalog && !refresh && Date.now() - lastScan < 30000) return catalog;
    scanPromise = scan()
      .then((result) => {
        catalog = result;
        lastScan = Date.now();
        return result;
      })
      .finally(() => {
        scanPromise = null;
      });
    return scanPromise;
  }
  async function getSample(id) {
    if (!records.has(id)) await getCatalog();
    const record = records.get(id);
    if (!record) return null;
    const values = [];
    let origin = null;
    let previous = null;
    const segments = [];
    const aggregates = new Map();
    let rowCount = 0;
    let keyOrder = [];
    for await (const row of rows(record.path)) {
      rowCount++;
      const time = number(row.mono_s) ?? number(row.elapsed_s);
      if (time === null) continue;
      origin ??= time;
      const t = time - origin;
      if (!previous || previous.phase !== row.phase) {
        segments.push({ phase: row.phase, start: t, end: t });
        previous = { phase: row.phase };
      } else segments[segments.length - 1].end = t;
      const point = { t, phase: row.phase, values: {} };
      for (const [key, label, unit, sensor] of CHANNELS) {
        const value = valid(row, key, sensor) ? number(row[key]) : null;
        point.values[key] = value;
        if (!aggregates.has(key))
          aggregates.set(key, {
            key,
            label,
            unit,
            count: 0,
            invalid: 0,
            min: Infinity,
            max: -Infinity,
            sum: 0,
          });
        const agg = aggregates.get(key);
        if (value === null) agg.invalid++;
        else {
          agg.count++;
          agg.sum += value;
          agg.min = Math.min(agg.min, value);
          agg.max = Math.max(agg.max, value);
        }
      }
      values.push(point);
      if (!keyOrder.length) keyOrder = Object.keys(row);
    }
    const channels = [...aggregates.values()]
      .filter((a) => a.count > 0)
      .map(({ sum, ...a }) => ({ ...a, mean: sum / a.count }));
    // Retain every raw point. Typical trial files are small; no smoothing or hidden imputation.
    const metadata = await json(resolve(record.folder, 'metadata.json'));
    const summary = await json(resolve(record.folder, 'summary.json'));
    const prediction = await json(resolve(record.folder, 'prediction.json'));
    const bytes = await readFile(await confined(record.path));
    const sha256 = createHash('sha256').update(bytes).digest('hex');
    return {
      id,
      readOnly: true,
      rowCount,
      columns: keyOrder,
      points: values,
      segments,
      channels,
      metadata,
      summary,
      prediction,
      sha256,
    };
  }
  return { getCatalog, getSample };
}
export function datasetPlugin() {
  const reader = createDatasetReader();
  const middleware = async (req, res, next) => {
    const url = new URL(req.url ?? '/', 'http://localhost');
    if (!url.pathname.startsWith('/api/dataset')) return next();
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    if (!['GET', 'HEAD'].includes(req.method)) {
      res.statusCode = 405;
      res.setHeader('Allow', 'GET, HEAD');
      res.end(JSON.stringify({ error: 'Dataset chỉ đọc. Không hỗ trợ sửa hoặc xóa.' }));
      return;
    }
    try {
      let payload;
      if (url.pathname === '/api/dataset')
        payload = await reader.getCatalog(url.searchParams.get('refresh') === '1');
      else if (url.pathname === '/api/dataset/sample') {
        payload = await reader.getSample(url.searchParams.get('id'));
        if (!payload) {
          res.statusCode = 404;
          payload = { error: 'Không tìm thấy mẫu trong danh mục data/.' };
        }
      } else {
        res.statusCode = 404;
        payload = { error: 'Endpoint không tồn tại.' };
      }
      res.end(req.method === 'HEAD' ? '' : JSON.stringify(payload));
    } catch {
      res.statusCode = 500;
      res.end(
        JSON.stringify({ error: 'Không đọc được dữ liệu. Kiểm tra thư mục data/ và quyền đọc.' }),
      );
    }
  };
  return {
    name: 'robonose-readonly-dataset',
    configureServer(server) {
      server.middlewares.use(middleware);
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware);
    },
  };
}

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  captureReducer,
  createCaptureState,
  captureBusy,
  interpretPrediction,
  pendingInference,
  displayIdentity,
} from '../src/testWorkflow.ts';

test('Thu mẫu test không cần danh tính, chờ Expose/Recover và chỉ hoàn tất sau đủ pha', () => {
  let state = createCaptureState();
  assert.equal(state.sampleId, null);
  state = captureReducer(state, { type: 'START', now: 0 });
  assert.equal(captureBusy(state), true);
  state = captureReducer(state, { type: 'TICK', now: 60000 });
  assert.equal(state.phase, 'WAIT_EXPOSURE');
  const waiting = state;
  state = captureReducer(state, { type: 'TICK', now: 999999 });
  assert.equal(state, waiting);
  state = captureReducer(state, { type: 'FINISH', sampleId: 'TEST-X' });
  assert.equal(state.phase, 'WAIT_EXPOSURE');
  state = captureReducer(state, { type: 'EXPOSE', now: 100000 });
  state = captureReducer(state, { type: 'TICK', now: 220000 });
  assert.equal(state.phase, 'WAIT_RECOVERY');
  state = captureReducer(state, { type: 'RECOVER', now: 300000 });
  state = captureReducer(state, { type: 'TICK', now: 360000 });
  assert.equal(state.phase, 'WAIT_FINISH');
  state = captureReducer(state, { type: 'FINISH', sampleId: 'TEST-X' });
  assert.equal(state.phase, 'COMPLETE');
  assert.equal(state.sampleId, 'TEST-X');
  assert.equal(captureBusy(state), false);
  state = captureReducer(state, { type: 'RESET' });
  assert.equal(state.phase, 'READY');
  assert.equal(state.sampleId, null);
});
test('Hủy phiên không tạo mẫu nhận diện; lệnh sai pha không đổi trạng thái', () => {
  let state = createCaptureState();
  assert.equal(captureReducer(state, { type: 'RECOVER', now: 5 }), state);
  state = captureReducer(state, { type: 'START', now: 0 });
  state = captureReducer(state, { type: 'TICK', now: 2000 });
  assert.equal(state.elapsed, 2);
  state = captureReducer(state, { type: 'ABORT' });
  assert.equal(state.phase, 'ABORTED');
  assert.equal(state.sampleId, null);
  assert.equal(captureReducer(state, { type: 'FINISH', sampleId: 'TEST-X' }), state);
  state = captureReducer(state, { type: 'START', now: 9000 });
  assert.equal(state.phase, 'BASELINE');
  assert.equal(state.elapsed, 0);
});
test('Thông số pha lỗi trở về protocol hợp lệ', () => {
  assert.deepEqual(createCaptureState(NaN, -3, Infinity).durations, {
    BASELINE: 60,
    EXPOSURE: 120,
    RECOVERY: 60,
  });
});
test('Kết luận nhận diện chỉ từ status và person đã chấp nhận', () => {
  const accepted = interpretPrediction({
    status: 'identity_accepted',
    prediction: {
      person: 'Tai',
      best_cosine_similarity: 0.91,
      similarity_threshold: 0.8,
      margin: 0.2,
      margin_threshold: 0.1,
    },
  });
  assert.equal(accepted.kind, 'matched');
  assert.equal(accepted.person, 'Nguyễn Văn Tài');
  assert.equal(accepted.similarity, 0.91);
  assert.equal(
    interpretPrediction({ prediction: { person: 'Tai', best_match: 'Tai' } }).kind,
    'unsupported',
  );
  assert.equal(
    interpretPrediction({
      status: 'identity_accepted',
      prediction: { person: null, best_match: 'Tai' },
    }).person,
    null,
  );
  assert.equal(
    interpretPrediction({ status: 'identity_accepted', prediction: { person: 'UNKNOWN' } }).kind,
    'unsupported',
  );
  assert.equal(
    interpretPrediction({ status: 'ranked_match_only', prediction: { person: 'Tai' } }).kind,
    'ranked_only',
  );
  assert.equal(displayIdentity('aDung'), 'aDung');
});
test('Unknown khác với thiếu kết quả, mẫu lỗi và chưa nối dịch vụ AI', () => {
  assert.equal(interpretPrediction(null).kind, 'no_result');
  assert.equal(
    interpretPrediction({
      status: 'identity_rejected',
      prediction: { best_match: 'Tai', best_cosine_similarity: 0 },
    }).kind,
    'unknown',
  );
  assert.equal(
    interpretPrediction({ status: 'quality_rejected', prediction: null }).kind,
    'quality_rejected',
  );
  const pending = pendingInference();
  assert.equal(pending.kind, 'integration_required');
  assert.equal(pending.person, null);
  assert.equal(pending.similarity, null);
});

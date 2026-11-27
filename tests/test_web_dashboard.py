import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from robonose_s3.inference import MockPredictor
from robonose_s3.session import Session
from robonose_s3.web_server import RoboNoseWebServer, TrialCatalog
from conftest import wait_until


def get_json(base, path):
    with urlopen(base + path, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base, path, payload):
    request = Request(base + path, data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=2) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_mock_predictor_unknown_and_rank_are_deterministic():
    predictor = MockPredictor()
    unknown = predictor.predict_identity("unknown-demo")
    assert unknown["model_backend"] == "MOCK"
    assert unknown["synthetic_prediction"] is True
    assert unknown["is_unknown"] is True and unknown["predicted_id"] is None
    first = predictor.compare("X", ["A", "B", "C", "D"])
    second = predictor.compare("X", ["A", "B", "C", "D"])
    assert [(item["candidate_id"], item["similarity"]) for item in first["ranking"]] == [
        (item["candidate_id"], item["similarity"]) for item in second["ranking"]]
    assert [item["rank"] for item in first["ranking"]] == [1, 2, 3, 4]


def test_web_serves_main_functions_and_uses_session_command_queue(tmp_path):
    session = Session(tmp_path / "data/simulation")
    web = RoboNoseWebServer(session, tmp_path / "data/simulation", port=0)
    session.start()
    base = web.start()
    try:
        with urlopen(base + "/", timeout=2) as response:
            page = response.read().decode("utf-8")
        assert all(value in page for value in (
            "Tín hiệu & thiết bị", "Điều khiển thu mẫu", "Dự đoán danh tính",
            "Đối sánh", "Danh sách mẫu", "Chọn mẫu", "Lưu lựa chọn"))
        assert "Kho mẫu chuẩn" not in page
        assert "5 cảm biến vật lý" in page
        assert "8 biểu đồ realtime" in page
        assert "Kéo dài recovery" not in page
        snapshot = get_json(base, "/api/snapshot?window=120")
        assert snapshot["mode"] == "SIMULATED" and len(snapshot["sensors"]) == 8
        assert snapshot["device"]["physical_sensor_count"] == 5
        assert snapshot["device_info"]["transport"] == "SIMULATED"
        assert snapshot["configuration"] == {
            "baseline_s": 60, "exposure_s": 120, "recovery_s": 60,
            "pump_pwm_pct": 80, "sampling_hz": 1,
            "runtime_editable": True, "source": "SIMULATION_CONFIG"}
        assert snapshot["actions"]["start"] is True
        status, queued = post_json(base, "/api/commands", {
            "action": "start", "request_id": "web-start-1"})
        assert status == 202 and queued["queued"] is True
        wait_until(lambda: session.snapshot()["phase"] == "BASELINE")
        assert get_json(base, "/api/snapshot?window=120")["phase"] == "BASELINE"
        try:
            post_json(base, "/api/commands", {"action": "not-a-command"})
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("Unsupported web command was accepted")
        try:
            post_json(base, "/api/commands", {"action": "extend", "argument": "30"})
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("Recovery extension should not be exposed by the web API")
        web.stop()
        assert not session.finished.is_set()  # Closing the web surface never stops acquisition.
    finally:
        if web.started:
            web.stop()
        session.post("quit")
        assert session.finished.wait(5)


def test_web_mock_identity_and_reference_comparison_jobs(tmp_path):
    session = Session(tmp_path / "data/simulation")
    web = RoboNoseWebServer(session, tmp_path / "data/simulation", port=0)
    session.start()
    base = web.start()
    try:
        status, identity = post_json(base, "/api/inference/identity", {"sample_id": "unknown-demo"})
        assert status == 202 and identity["state"] == "QUEUED"
        candidates = ["A", "B", "C", "D", "E", "F"]
        status, comparison = post_json(base, "/api/inference/compare", {
            "reference_id": "X", "candidate_ids": candidates})
        assert status == 202 and comparison["state"] == "QUEUED"
        wait_until(lambda: len(get_json(base, "/api/inference/results?after=0")["jobs"]) == 2 and
                   all(job["state"] == "SUCCEEDED" for job in
                       get_json(base, "/api/inference/results?after=0")["jobs"]))
        jobs = get_json(base, "/api/inference/results?after=0")["jobs"]
        result_by_task = {job["task"]: job["result"] for job in jobs}
        assert result_by_task["identity"]["is_unknown"] is True
        assert "coffee_check" not in next(job for job in jobs if job["task"] == "identity")
        ranking = result_by_task["reference_comparison"]["ranking"]
        assert {item["candidate_id"] for item in ranking} == set(candidates)
        assert [item["rank"] for item in ranking] == list(range(1, len(candidates) + 1))
    finally:
        web.stop()
        session.post("quit")
        assert session.finished.wait(5)


def test_comparison_requires_unique_candidates():
    predictor = MockPredictor()
    assert len(predictor.compare("X", ["A"])["ranking"]) == 1
    with pytest.raises(ValueError, match="At least one"):
        predictor.compare("X", [])
    with pytest.raises(ValueError, match="must be unique"):
        predictor.compare("X", ["A", "A"])


def test_coffee_job_does_not_call_identity_predictor(tmp_path, monkeypatch):
    trial_id = "44444444-4444-4444-8444-444444444444"
    folder = tmp_path / "session" / "trials" / "coffee"
    folder.mkdir(parents=True)
    (folder / "metadata.json").write_text(json.dumps({
        "trial_id": trial_id, "status": "COMPLETE", "export_finalized": True, "mode": "HARDWARE",
    }), encoding="utf-8")
    raw_path = folder / "raw.csv"
    raw_path.touch()

    class UnavailableIdentity(MockPredictor):
        def predict_identity(self, sample_id):
            raise RuntimeError("Identity backend offline")

    def check_coffee(path):
        assert path == str(raw_path.resolve())
        return {"status": "PREDICTED", "has_coffee": True, "model": "test-model"}

    web = RoboNoseWebServer(None, tmp_path, port=0, predictor=UnavailableIdentity())
    monkeypatch.setattr(web.app.inference, "_check_coffee", check_coffee)
    base = web.start()
    try:
        with pytest.raises(HTTPError) as error:
            post_json(base, "/api/inference/coffee", {"sample_id": "unknown"})
        assert error.value.code == 400
        assert post_json(base, "/api/inference/coffee", {"sample_id": trial_id})[0] == 202
        assert post_json(base, "/api/inference/identity", {"sample_id": trial_id})[0] == 202
        wait_until(lambda: len(get_json(base, "/api/inference/results")["jobs"]) == 2 and
                   all(job["state"] in {"SUCCEEDED", "FAILED"}
                       for job in get_json(base, "/api/inference/results")["jobs"]))
        jobs = {job["task"]: job for job in get_json(base, "/api/inference/results")["jobs"]}
        assert jobs["coffee"]["result"]["has_coffee"] is True
        assert jobs["identity"]["state"] == "FAILED"
    finally:
        web.stop()


def test_trial_catalog_reports_saved_qc_status(tmp_path):
    folder = tmp_path / "2026-11-19" / "2026-11-19" / "session" / "trials" / "sample"
    folder.mkdir(parents=True)
    (folder / "metadata.json").write_text(json.dumps({
        "trial_id": "11111111-1111-4111-8111-111111111111",
        "name": "Mẫu A", "status": "COMPLETE", "mode": "SIMULATED",
        "session_id": "22222222-2222-4222-8222-222222222222",
        "export_finalized": True}), encoding="utf-8")
    (folder / "summary.json").write_text(json.dumps({
        "quality": "INSUFFICIENT", "quality_reasons": ["fixture"]}), encoding="utf-8")
    result = TrialCatalog(tmp_path).list()
    assert result[0]["quality"] == "INSUFFICIENT"
    assert result[0]["quality_reasons"] == ["fixture"]


def test_trial_catalog_combines_read_only_roots_without_duplicate_uuid(tmp_path):
    trial_id = "11111111-1111-4111-8111-111111111111"
    roots = [tmp_path / "live", tmp_path / "archive"]
    for index, root in enumerate(roots):
        folder = root / "2026-11-19" / f"session-{index}" / "trials" / "sample"
        folder.mkdir(parents=True)
        (folder / "metadata.json").write_text(json.dumps({
            "trial_id": trial_id, "name": "Mẫu A", "status": "COMPLETE",
            "mode": "HARDWARE" if index == 0 else "SIMULATED",
            "session_id": f"session-{index}"}), encoding="utf-8")
    result = TrialCatalog(roots).list()
    assert len(result) == 1 and result[0]["trial_id"] == trial_id
    assert result[0]["mode"] == "HARDWARE"  # Root order is source priority.


def test_identity_api_rejects_known_aborted_trial_before_model(tmp_path):
    trial_id = "33333333-3333-4333-8333-333333333333"
    folder = tmp_path / "data/simulation/2026-11-19/session/trials/aborted"
    folder.mkdir(parents=True)
    (folder / "metadata.json").write_text(json.dumps({
        "trial_id": trial_id, "name": "Mẫu hủy", "status": "ABORTED",
        "mode": "SIMULATED", "session_id": "session", "export_finalized": True
    }), encoding="utf-8")
    session = Session(tmp_path / "data/simulation")
    web = RoboNoseWebServer(session, tmp_path / "data/simulation", port=0)
    session.start(); base = web.start()
    try:
        with pytest.raises(HTTPError) as caught:
            post_json(base, "/api/inference/identity", {"sample_id": trial_id})
        assert caught.value.code == 400
        body = json.loads(caught.value.read().decode("utf-8"))
        assert "chỉ mẫu COMPLETE" in body["error"]
    finally:
        web.stop(); session.post("quit"); assert session.finished.wait(5)

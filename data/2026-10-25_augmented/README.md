# Dữ liệu mùi đã làm giàu

- Nguồn: `data/2026-10-25/`
- Phiên thật đạt kiểm tra chất lượng: 6
- Phiên bị loại: 1
- Tổng mẫu gồm bản thật và augmented: 126
- Tổng dòng tín hiệu: 30240
- Số mẫu theo người: {'Dung': 21, 'Minh': 21, 'Quy': 21, 'Tai': 63}

## Tệp đầu ra

- `augmented_signals.csv`: tín hiệu đã chuẩn hóa baseline, cố định 60/120/60 mẫu cho BASELINE/EXPOSURE/RECOVERY.
- `feature_vectors.csv`: mười đặc trưng gốc, z-score và vector `v_01..v_10` đã chuẩn hóa L2 để tính cosine similarity.
- `person_prototypes.csv`: vector đại diện tính từ các phiên thật, không dùng bản augmented như phiên độc lập.
- `identity_profiles.csv`: centroid cân bằng theo phiên và ngưỡng cosine/margin của từng người.
- `identity_model.json`: model vector hoàn chỉnh để kiểm tra một mẫu mới có phù hợp hay không.
- `run_quality.csv`: kết quả kiểm tra chất lượng và lý do loại phiên.
- `scaler.json`: mean/std học từ các phiên thật để áp dụng cho mẫu mới.
- `manifest.json`: cấu hình tái lập pipeline.

## Augmentation

Mỗi biến thể dùng cùng hệ số cho cả ba cảm biến: amplitude scaling 0.97–1.03, time stretching 0.98–1.02, dịch ±2 mẫu và cộng 0.10–0.30 lần residual noise của baseline. Các pha không bị đảo hoặc trộn.

## Lưu ý

Ba người Dung, Minh và Quy chỉ có một phiên thật. Các mẫu augmented không thay thế được phiên đo thật và không được dùng để chia ngẫu nhiên giữa train/test nếu cùng `source_run`.

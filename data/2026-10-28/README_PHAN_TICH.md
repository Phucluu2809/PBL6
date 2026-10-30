# Phân tích dữ liệu phát hiện mùi cà phê trên người

README này tổng hợp trực tiếp phạm vi dữ liệu, pipeline phân tích, biểu đồ và kết quả của bộ dữ liệu ngày **2026-10-28**. Mục tiêu chính là đánh giá tín hiệu e-nose có đủ thông tin để phân biệt **người không mang cà phê** và **người có mùi cà phê** hay không.

## 1. Kết luận nhanh

Bộ dữ liệu có **17 phiên hoàn tất** và **7,661 dòng dữ liệu thô**:

| Nhóm dữ liệu | Số phiên | Vai trò |
|---|---:|---|
| Người không cà phê | 7 | Nhãn 0; gồm 5 Tài, 1 Minh, 1 Quy |
| Người có cà phê | 4 | Nhãn 1; hiện chỉ có Tài |
| Cà phê riêng | 4 | Đối chứng cà phê ít/nhiều |
| Không khí | 1 | Mẫu trắng môi trường |
| Phiên paired đặc biệt | 1 | Baseline Tài → Exposure Tài+cà phê |

Các kết quả chính:

- **15/17 phiên đạt QC**; hai phiên `CF_nhieu` cần xem lại vì baseline không ổn định.
- Có **198 lỗi đọc rải rác**, nhưng tỷ lệ dữ liệu hợp lệ của các pha lõi vẫn trên 90% ở tất cả phiên.
- Nhiệt độ baseline thay đổi **30.75–33.47 °C**, độ ẩm **67.83–71.10%** và áp suất **1011.75–1018.95 hPa**.
- Hai lần đo cà phê ít có cosine **0.974**; cà phê nhiều **0.973**; hai phiên `TaivsCF` **0.986**.
- Năm phiên Tài không cà phê có cosine trung vị chỉ **0.451**, cho thấy độ lặp lại nội-người còn thấp.
- BME688 và MQ3-1 có thay đổi trung bình giữa hai trạng thái Tài, nhưng các điểm vẫn chồng lấn; chưa có cảm biến đơn lẻ tạo ranh giới phát hiện sạch.
- Kết luận hiện tại: **có tín hiệu để tiếp tục nghiên cứu**, nhưng chưa đủ dữ liệu để xây bộ phát hiện cà phê trên người có khả năng tổng quát hóa.

## 2. Phạm vi dữ liệu được sử dụng

Mỗi thư mục có `raw.csv`, `events.csv`, `metadata.json` và `summary.json` được xem là một phiên độc lập. `report_assets/` chỉ chứa biểu đồ đầu ra và không được tính là dữ liệu.

Hai khối đo trong ngày:

```text
Khối 1 (12:58–14:13): Không khí → CF ít → Tài → Tài → paired Tài/CF → CF nhiều → Tài+CF → Tài+CF
Khối 2 (22:00–23:18): Minh → Tài → Tài → Tài → Quy → CF nhiều → Tài+CF nhiều → Tài+CF ít → CF ít
```

Ba pha dùng để phân tích:

| Pha | Thời gian danh định | Vai trò |
|---|---:|---|
| Baseline | 60 giây | Ước lượng mức nền riêng của từng cảm biến |
| Exposure | 120 giây | Quan sát đáp ứng khi tiếp xúc mẫu |
| Recovery | 60 giây | Kiểm tra khả năng quay lại baseline |

Các pha `MONITOR` và `WAIT_*` được giữ để kiểm tra quy trình, nhưng không dùng làm đặc trưng nhận dạng. Phiên `BaseTai_ExposeTaivsCF` được giữ như phép đo paired và **không tính là một mẫu nhãn 1 độc lập** trong so sánh nhị phân chính.

## 3. Pipeline phân tích

### 3.1. Gán nhãn

| Nhãn thư mục | `sample_type` | `coffee_present` | `subject_id` |
|---|---|:---:|---|
| `Tai`, `aMinh`, `aQuy` | `HUMAN_ONLY` | 0 | Tài / Minh / Quy |
| `TaivsCF*` | `HUMAN_COFFEE` | 1 | Tài |
| `CF_it`, `CF_nhieu` | `COFFEE_ONLY` | NA | NA |
| `khongkhi` | `AIR` | NA | NA |
| `BaseTai_ExposeTaivsCF` | `PAIRED` | Theo pha | Tài |

Không tự động gán BASELINE của mọi phiên thành nhãn 0. Baseline thông thường chỉ là mức nền dùng để hiệu chỉnh tín hiệu.

### 3.2. Lọc dữ liệu hợp lệ

BME688 chỉ được giữ khi:

```text
bme_status == "OK"
bme_fresh == True
gas_valid == True
heater_stable == True
new_data == True
```

MQ chỉ được giữ khi `status=OK`, dữ liệu `fresh` và `quality=OK`. Hai giá trị MQ3 âm được đánh dấu `NEGATIVE` nên không được dùng khi tính đặc trưng.

### 3.3. Chuẩn hóa theo baseline

Mỗi phiên và mỗi cảm biến được chuẩn hóa độc lập bằng median BASELINE:

```text
response_pct = 100 × (signal - median_baseline) / |median_baseline|
```

Số âm nghĩa là tín hiệu thấp hơn baseline; số dương nghĩa là tín hiệu cao hơn baseline. Dấu âm không phải giá trị vật lý âm.

### 3.4. Đặc trưng được trích xuất

| Nhóm | Đặc trưng |
|---|---|
| Cường độ | Mean, middle mean, Q10, Q90, min, max |
| Động học | Slope trong exposure |
| Tích phân | AUC của exposure |
| Phục hồi | Trung bình 10 mẫu cuối recovery |
| Chất lượng | Tỷ lệ hợp lệ từng cảm biến/từng pha, baseline stability |

### 3.5. Nguyên tắc đánh giá

Một phiên hoàn chỉnh là một mẫu độc lập. Không chia ngẫu nhiên từng dòng 1 Hz vào train/test và không tách phiên paired thành hai mẫu độc lập. Với dữ liệu hiện tại chỉ có một ngày và nhóm dương chỉ có Tài, PCA/classification nếu có chỉ mang tính thăm dò, không phải bằng chứng hiệu năng triển khai.

## 4. Kiểm tra chất lượng dữ liệu

**Phương pháp:** tính tỷ lệ hợp lệ cho từng cảm biến trong BASELINE, EXPOSURE và RECOVERY; lấy tỷ lệ nhỏ nhất làm chỉ báo bảo thủ của phiên. Đồng thời đếm `read_error` trong `events.csv` và đọc cờ baseline stability từ `summary.json`.

![Chất lượng dữ liệu và lỗi đọc](./report_assets/04_chat_luong_va_loi_doc.svg)

**Kết quả:**

- Cả 17 phiên đều có tỷ lệ hợp lệ tối thiểu trên 90%, nhưng chỉ **15 phiên đạt đầy đủ** khi xét thêm baseline stability.
- `CF_nhieu_20261028_135336_dfdeeb8c63c34ceb8e7c36d906385b8f`: baseline không ổn định.
- `CF_nhieu_20261028_225145_a3b36b8b17f74a27a78e9cdf0bf801c9`: baseline không ổn định.
- Tổng số lỗi đọc: **198**; nhiều nhất là MQ135-1 (56), MQ3-1 (53) và MQ135-2 (51).
- Hai giá trị âm chỉ xuất hiện đơn lẻ ở MQ3 và đều có `quality=NEGATIVE`; đây là lỗi điểm, không phải toàn bộ kênh bị âm.
- Phiên `CF_nhieu` buổi chiều bất ổn ở BME gas; phiên `CF_nhieu` buổi tối bất ổn ở độ ẩm. Không nên dùng hai phiên này làm bằng chứng chính cho đáp ứng đã hiệu chỉnh nền.

## 5. Điều kiện môi trường và drift theo thời gian

**Phương pháp:** lấy median nhiệt độ, độ ẩm và áp suất trong BASELINE của từng phiên, sau đó sắp theo giờ bắt đầu.

![Điều kiện môi trường theo thời gian](./report_assets/05_moi_truong_theo_thoi_gian.svg)

**Kết quả:**

- Nhiệt độ baseline biến thiên **30.75–33.47 °C**.
- Độ ẩm baseline biến thiên **67.83–71.10%**.
- Áp suất baseline biến thiên **1011.75–1018.95 hPa**.
- Khối buổi tối bắt đầu ở điều kiện khác rõ khối buổi chiều. Vì nhãn và thời điểm đo chưa cân bằng, mô hình có thể học môi trường thay vì mùi cà phê.

## 6. Heatmap đáp ứng của toàn bộ phiên

**Phương pháp:** tính đáp ứng trung bình trong 120 giây EXPOSURE cho năm cảm biến, sau đó đặt các phiên theo đúng thứ tự thời gian.

![Heatmap đáp ứng toàn bộ phiên](./report_assets/01_heatmap_dap_ung_toan_bo.svg)

**Kết quả:**

- BME688 thường giảm khi gặp cà phê; MQ3-1 thường tăng, nhưng biên độ thay đổi mạnh giữa các lần đo.
- Phiên không khí vẫn có MQ135-1 tăng rõ, cho thấy carry-over, thao tác đổi ống hoặc drift chưa được kiểm soát hoàn toàn.
- Hai kênh MQ135 và hai kênh MQ3 cùng loại không tạo đáp ứng tương đồng ổn định.
- Không có một mẫu màu duy nhất tách sạch toàn bộ Tài+cà phê khỏi Tài không cà phê.

## 7. So sánh Tài có và không có cà phê

**Phương pháp:** dùng 5 phiên Tài thuần làm nhóm không cà phê và 4 phiên `TaivsCF*` làm nhóm có cà phê. Phiên paired đặc biệt không được tính như mẫu độc lập. Mỗi điểm là trung bình EXPOSURE của một phiên.

![So sánh Tài có và không có cà phê](./report_assets/02_tai_co_khong_ca_phe.svg)

Giá trị trung bình:

| Cảm biến | Tài không CF | Tài có CF | Chênh lệch có − không |
|---|---:|---:|---:|
| BME688 gas | -1.04% | -1.94% | -0.89 điểm % |
| MQ135-1 | 0.83% | 0.12% | -0.71 điểm % |
| MQ3-1 | 0.47% | 0.98% | 0.51 điểm % |
| MQ135-2 | 0.44% | 0.08% | -0.36 điểm % |
| MQ3-2 | 0.01% | -0.16% | -0.17 điểm % |

**Kết quả:**

- BME688 giảm mạnh hơn và MQ3-1 tăng hơn ở nhóm Tài+cà phê về trung bình.
- Tuy nhiên, điểm của hai nhóm vẫn chồng lấn trên cả năm cảm biến.
- MQ135-1 bị chi phối bởi một phiên Tài thuần tăng mạnh, nên trung bình nhóm không cà phê cao hơn nhóm có cà phê.
- Chưa thể đặt một threshold đơn cảm biến đáng tin cậy. Cần kết hợp nhiều đặc trưng và thu thêm dữ liệu paired khác ngày.

## 8. So sánh các nhóm mẫu

**Phương pháp:** gộp các phiên cùng nhãn và tính trung bình đáp ứng EXPOSURE. Các nhóm chỉ có một phiên được xem là mô tả, không phải ước lượng thống kê.

![Heatmap trung bình theo nhóm](./report_assets/03_heatmap_trung_binh_nhom.svg)

**Kết quả:**

- Cà phê riêng tác động rõ nhất lên BME688 và MQ3-1.
- Thứ tự cà phê ít–nhiều không ổn định giữa hai khối thời gian, nên chưa chứng minh được quan hệ liều–đáp ứng.
- Hai phiên `TaivsCF` không ghi mức cà phê khá giống nhau, nhưng `TaivsCF_it` và `TaivsCF_nhieu` không giữ cùng hướng trên mọi cảm biến.
- Phiên paired cho thấy thay đổi khi chuyển từ Tài sang Tài+cà phê, nhưng vẫn đồng thời chứa ảnh hưởng thứ tự pha và thời gian.

## 9. Động học BME688 và recovery

**Phương pháp:** với mỗi phiên, tính Q10, Q90, slope, AUC trong EXPOSURE và trung bình 10 mẫu cuối RECOVERY của BME688.

| Phiên | Nhãn | Q10 EXP | Q90 EXP | Slope (%/s) | AUC (%·s) | Cuối recovery |
|---|---|---:|---:|---:|---:|---:|
| `khongkhi_20261028_125835_c727a4b77a3745eaac01a4e8b43f601f` | Không khí | -0.25% | 0.50% | -0.0007 | 12.86 | -0.44% |
| `CF_it_20261028_130942_89958870da3a414b996875ce9bb53232` | Cà phê ít | -9.51% | -3.91% | -0.0387 | -810.52 | -1.51% |
| `Tai_20261028_132052_c0f2cb166de84dafa9f32ad51b027407` | Tài | -3.98% | -0.91% | 0.0156 | -273.05 | -0.34% |
| `Tai_20261028_133044_f11c5d5df1e5465ab58d4fb146b042f7` | Tài | -1.82% | -0.55% | -0.0013 | -141.97 | -0.35% |
| `BaseTai_ExposeTaivsCF_20261028_134433_8624967b0af04e46b1423e34d4089175` | Tài nền → Tài + cà phê | -2.91% | -0.61% | -0.0067 | -180.25 | -1.66% |
| `CF_nhieu_20261028_135336_dfdeeb8c63c34ceb8e7c36d906385b8f` | Cà phê nhiều | -5.07% | 0.56% | -0.0468 | -286.52 | -0.30% |
| `TaivsCF_20261028_140100_1bff9ed3f85e48aba0e88fbce6d069a1` | Tài + cà phê | -5.55% | -2.07% | 0.0146 | -489.41 | -0.54% |
| `TaivsCF_20261028_140732_6ebb709e66fe428d8a409526c6953b89` | Tài + cà phê | -6.36% | -2.27% | -0.0073 | -476.40 | -0.23% |
| `aMinh_20261028_220050_fc400e4c0b5042ac9895362f00432bc4` | Minh | -7.57% | -4.33% | -0.0153 | -830.31 | -0.84% |
| `Tai_20261028_221033_4d88fcedc38343888cb6f5a4b4763339` | Tài | -1.04% | -0.12% | 0.0028 | -65.58 | -1.56% |
| `Tai_20261028_221651_451fe4ecf7e040cd8fff14d31f84d574` | Tài | -3.80% | -0.90% | 0.0103 | -221.34 | -0.45% |
| `Tai_20261028_222430_7a1dbcddcf764f6abea499bbb1b7a6df` | Tài | -0.24% | 1.28% | 0.0149 | 81.18 | 0.21% |
| `aQuy_20261028_223510_9c3f50c498fd48cdb4e2320b3131b781` | Quy | -1.53% | -0.55% | 0.0035 | -120.61 | 1.27% |
| `CF_nhieu_20261028_225145_a3b36b8b17f74a27a78e9cdf0bf801c9` | Cà phê nhiều | -6.42% | -4.21% | -0.0053 | -650.69 | -1.58% |
| `TaivsCF_nhieu_20261028_225757_2f3ce2dc50b841b2afd5fe04460dfa3a` | Tài + cà phê nhiều | 0.50% | 1.39% | 0.0058 | 111.05 | 1.43% |
| `TaivsCF_it_20261028_230521_c569d712285e4b26b742e40bd22abfd7` | Tài + cà phê ít | -1.54% | 0.25% | -0.0014 | -72.47 | 0.21% |
| `CF_it_20261028_231123_f244e3adf50341a7a662dca618aaa7dd` | Cà phê ít | -2.83% | -1.18% | 0.0146 | -236.76 | -0.78% |

**Kết quả:**

- Cùng một nhãn có thể khác nhau về slope và mức recovery, cho thấy chỉ dùng exposure mean sẽ làm mất thông tin động học.
- Một số phiên cuối recovery vẫn lệch khỏi baseline; purge và thời gian hồi phục cần được chuẩn hóa trước khi thu bộ dữ liệu chính thức.
- Phiên paired nên được phân tích riêng theo chênh lệch đặc trưng giữa trạng thái Tài nền và Tài+cà phê, không đưa trực tiếp vào tập phân loại như một run bình thường.

## 10. Độ lặp lại và tính nhất quán của cảm biến

**Phương pháp:** mỗi phiên được nén thành vector 5 chiều gồm đáp ứng EXPOSURE trung bình của năm kênh; cosine được tính giữa các phiên cùng nhãn.

| Nhãn có lặp | Số phiên | Cosine trung vị | Cosine nhỏ nhất |
|---|---:|---:|---:|
| Cà phê ít | 2 | 0.974 | 0.974 |
| Cà phê nhiều | 2 | 0.973 | 0.973 |
| Tài | 5 | 0.451 | -0.655 |
| Tài + cà phê | 2 | 0.986 | 0.986 |

**Kết quả:**

- MQ135-1 ↔ MQ135-2 có tương quan **r=0.020**; MQ3-1 ↔ MQ3-2 có **r=0.035**.
- Tương quan gần 0 cho thấy hai cảm biến cùng loại chưa hoạt động như các bản sao tương đương; cần kiểm tra đấu nối, vị trí, hiệu chuẩn và độ ổn định từng kênh.
- Độ lặp lại cao của cặp cà phê không đủ bù cho độ lặp lại thấp của Tài thuần và số phiên quá ít.

## 11. Trả lời câu hỏi nghiên cứu

### Tín hiệu có phát hiện được cà phê riêng không?

**Có dấu hiệu rõ.** Cà phê riêng thường làm BME688 giảm và MQ3-1 tăng, hai lần lặp cùng mức có hướng fingerprint tương đối giống nhau. Tuy nhiên, hai phiên cà phê nhiều có baseline không ổn định nên chưa thể dùng làm bằng chứng định lượng mạnh.

### Có phân biệt được người có cà phê và không có cà phê không?

**Chưa đủ để kết luận.** Trung bình hai nhóm khác nhau trên BME688 và MQ3-1, nhưng phân bố vẫn chồng lấn. Dữ liệu chỉ có một ngày và nhóm dương chỉ có Tài.

### Có thể huấn luyện mô hình ngay không?

Có thể chạy Logistic Regression hoặc SVM tuyến tính như một kiểm tra kỹ thuật, nhưng kết quả không đại diện hiệu năng thực tế. Không nên dùng Random Forest/UMAP hoặc ROC-AUC làm bằng chứng chính với 9 phiên Tài nhị phân và chưa có test khác ngày.

## 12. Hạn chế của kết quả

1. Nhóm có cà phê chỉ có Tài; chưa đánh giá được cà phê trên người khác.
2. Minh và Quy chỉ có phiên âm tính, tạo nguy cơ subject leakage nếu gộp vào mô hình nhị phân.
3. Dữ liệu chỉ có một ngày và hai khối môi trường khác nhau.
4. Hai phiên cà phê nhiều có baseline không ổn định.
5. Đổi đầu ống và purge thủ công làm thời gian chờ không đồng nhất.
6. Hai cặp cảm biến cùng loại có tương quan rất thấp.
7. Số phiên ít hơn nhiều so với số đặc trưng ứng viên, nên feature selection và mô hình phức tạp dễ overfit.

## 13. Thiết kế thu thập tiếp theo

Mỗi người cần được đo paired ở cả hai trạng thái:

| Người | Không cà phê | Có cà phê ít | Có cà phê nhiều |
|---|:---:|:---:|:---:|
| Tài | Có | Có | Có |
| Minh | Có | Có | Có |
| Quy | Có | Có | Có |
| Người mới | Có | Có | Có |

Nên thu tối thiểu 10–15 phiên thật mỗi trạng thái/người trên nhiều ngày, cố định vị trí cơ thể, lượng cà phê, thời gian sau tiếp xúc, khoảng cách đầu hút, lưu lượng khí và quy trình purge. Đánh giá cuối cùng phải tách theo ngày và theo người.

## 14. Biểu đồ chi tiết từng phiên

Các biểu đồ dưới đây được thu gọn để README chính dễ đọc.

<details>
<summary><strong>Không khí</strong> — 12:58:35 — Đạt QC</summary>

![Tín hiệu gốc Không khí](./khongkhi_20261028_125835_c727a4b77a3745eaac01a4e8b43f601f/signals.png)

![Tín hiệu chuẩn hóa Không khí](./khongkhi_20261028_125835_c727a4b77a3745eaac01a4e8b43f601f/normalized.png)

</details>

<details>
<summary><strong>Cà phê ít</strong> — 13:09:42 — Đạt QC</summary>

![Tín hiệu gốc Cà phê ít](./CF_it_20261028_130942_89958870da3a414b996875ce9bb53232/signals.png)

![Tín hiệu chuẩn hóa Cà phê ít](./CF_it_20261028_130942_89958870da3a414b996875ce9bb53232/normalized.png)

</details>

<details>
<summary><strong>Tài</strong> — 13:20:52 — Đạt QC</summary>

![Tín hiệu gốc Tài](./Tai_20261028_132052_c0f2cb166de84dafa9f32ad51b027407/signals.png)

![Tín hiệu chuẩn hóa Tài](./Tai_20261028_132052_c0f2cb166de84dafa9f32ad51b027407/normalized.png)

</details>

<details>
<summary><strong>Tài</strong> — 13:30:44 — Đạt QC</summary>

![Tín hiệu gốc Tài](./Tai_20261028_133044_f11c5d5df1e5465ab58d4fb146b042f7/signals.png)

![Tín hiệu chuẩn hóa Tài](./Tai_20261028_133044_f11c5d5df1e5465ab58d4fb146b042f7/normalized.png)

</details>

<details>
<summary><strong>Tài nền → Tài + cà phê</strong> — 13:44:33 — Đạt QC</summary>

![Tín hiệu gốc Tài nền → Tài + cà phê](./BaseTai_ExposeTaivsCF_20261028_134433_8624967b0af04e46b1423e34d4089175/signals.png)

![Tín hiệu chuẩn hóa Tài nền → Tài + cà phê](./BaseTai_ExposeTaivsCF_20261028_134433_8624967b0af04e46b1423e34d4089175/normalized.png)

</details>

<details>
<summary><strong>Cà phê nhiều</strong> — 13:53:36 — Cần xem lại</summary>

![Tín hiệu gốc Cà phê nhiều](./CF_nhieu_20261028_135336_dfdeeb8c63c34ceb8e7c36d906385b8f/signals.png)

![Tín hiệu chuẩn hóa Cà phê nhiều](./CF_nhieu_20261028_135336_dfdeeb8c63c34ceb8e7c36d906385b8f/normalized.png)

</details>

<details>
<summary><strong>Tài + cà phê</strong> — 14:01:00 — Đạt QC</summary>

![Tín hiệu gốc Tài + cà phê](./TaivsCF_20261028_140100_1bff9ed3f85e48aba0e88fbce6d069a1/signals.png)

![Tín hiệu chuẩn hóa Tài + cà phê](./TaivsCF_20261028_140100_1bff9ed3f85e48aba0e88fbce6d069a1/normalized.png)

</details>

<details>
<summary><strong>Tài + cà phê</strong> — 14:07:32 — Đạt QC</summary>

![Tín hiệu gốc Tài + cà phê](./TaivsCF_20261028_140732_6ebb709e66fe428d8a409526c6953b89/signals.png)

![Tín hiệu chuẩn hóa Tài + cà phê](./TaivsCF_20261028_140732_6ebb709e66fe428d8a409526c6953b89/normalized.png)

</details>

<details>
<summary><strong>Minh</strong> — 22:00:50 — Đạt QC</summary>

![Tín hiệu gốc Minh](./aMinh_20261028_220050_fc400e4c0b5042ac9895362f00432bc4/signals.png)

![Tín hiệu chuẩn hóa Minh](./aMinh_20261028_220050_fc400e4c0b5042ac9895362f00432bc4/normalized.png)

</details>

<details>
<summary><strong>Tài</strong> — 22:10:33 — Đạt QC</summary>

![Tín hiệu gốc Tài](./Tai_20261028_221033_4d88fcedc38343888cb6f5a4b4763339/signals.png)

![Tín hiệu chuẩn hóa Tài](./Tai_20261028_221033_4d88fcedc38343888cb6f5a4b4763339/normalized.png)

</details>

<details>
<summary><strong>Tài</strong> — 22:16:51 — Đạt QC</summary>

![Tín hiệu gốc Tài](./Tai_20261028_221651_451fe4ecf7e040cd8fff14d31f84d574/signals.png)

![Tín hiệu chuẩn hóa Tài](./Tai_20261028_221651_451fe4ecf7e040cd8fff14d31f84d574/normalized.png)

</details>

<details>
<summary><strong>Tài</strong> — 22:24:30 — Đạt QC</summary>

![Tín hiệu gốc Tài](./Tai_20261028_222430_7a1dbcddcf764f6abea499bbb1b7a6df/signals.png)

![Tín hiệu chuẩn hóa Tài](./Tai_20261028_222430_7a1dbcddcf764f6abea499bbb1b7a6df/normalized.png)

</details>

<details>
<summary><strong>Quy</strong> — 22:35:10 — Đạt QC</summary>

![Tín hiệu gốc Quy](./aQuy_20261028_223510_9c3f50c498fd48cdb4e2320b3131b781/signals.png)

![Tín hiệu chuẩn hóa Quy](./aQuy_20261028_223510_9c3f50c498fd48cdb4e2320b3131b781/normalized.png)

</details>

<details>
<summary><strong>Cà phê nhiều</strong> — 22:51:45 — Cần xem lại</summary>

![Tín hiệu gốc Cà phê nhiều](./CF_nhieu_20261028_225145_a3b36b8b17f74a27a78e9cdf0bf801c9/signals.png)

![Tín hiệu chuẩn hóa Cà phê nhiều](./CF_nhieu_20261028_225145_a3b36b8b17f74a27a78e9cdf0bf801c9/normalized.png)

</details>

<details>
<summary><strong>Tài + cà phê nhiều</strong> — 22:57:57 — Đạt QC</summary>

![Tín hiệu gốc Tài + cà phê nhiều](./TaivsCF_nhieu_20261028_225757_2f3ce2dc50b841b2afd5fe04460dfa3a/signals.png)

![Tín hiệu chuẩn hóa Tài + cà phê nhiều](./TaivsCF_nhieu_20261028_225757_2f3ce2dc50b841b2afd5fe04460dfa3a/normalized.png)

</details>

<details>
<summary><strong>Tài + cà phê ít</strong> — 23:05:21 — Đạt QC</summary>

![Tín hiệu gốc Tài + cà phê ít](./TaivsCF_it_20261028_230521_c569d712285e4b26b742e40bd22abfd7/signals.png)

![Tín hiệu chuẩn hóa Tài + cà phê ít](./TaivsCF_it_20261028_230521_c569d712285e4b26b742e40bd22abfd7/normalized.png)

</details>

<details>
<summary><strong>Cà phê ít</strong> — 23:11:23 — Đạt QC</summary>

![Tín hiệu gốc Cà phê ít](./CF_it_20261028_231123_f244e3adf50341a7a662dca618aaa7dd/signals.png)

![Tín hiệu chuẩn hóa Cà phê ít](./CF_it_20261028_231123_f244e3adf50341a7a662dca618aaa7dd/normalized.png)

</details>

## 15. File tái lập phân tích

Báo cáo và toàn bộ SVG tổng hợp được sinh bởi:

- `analysis/generate_2026_10_28_report.py`

Chạy lại từ thư mục gốc repository:

```powershell
python analysis/generate_2026_10_28_report.py
```

Các đầu ra chính:

- `data/2026-10-28/README_PHAN_TICH.md`
- `data/2026-10-28/report_assets/*.svg`

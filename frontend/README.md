# RoboNose BioID — nhận diện người bằng mùi cơ thể

Workspace React + TypeScript cho PBL6. Cách tổ chức tương tự nhận diện khuôn mặt: **hồ sơ người → thu trực tiếp mùi cơ thể → mẫu tham chiếu → đối chiếu danh tính**. Không chia vị trí cơ thể trong giao diện thu mẫu.

Ba tài khoản và hồ sơ mặc định:

| Mã hồ sơ | Họ tên           | Vai trò UI mặc định          |
| -------- | ---------------- | ---------------------------- |
| P001     | Nguyễn Văn Tài   | Super Admin, Operator        |
| P002     | Nguyễn Văn Dương | Admin, Researcher            |
| P003     | Lưu Hoàng Phúc   | Researcher, Operator, Tester |

Email `@robonose.local` là địa chỉ placeholder, không phải email thật. Sáu vai trò xem trước có trong topbar, bao gồm Tester; không tạo thêm người giả để minh họa từng role.

## Ứng dụng kiểm tra mùi — role Tester

Chọn **Tester** ở topbar hoặc màn hình đăng nhập để tự mở `/#/test`. Phiên trình duyệt mới mặc định Tester. Phiên cũ giữ role đang dùng; có thể đổi sang Tester hoặc chọn **Mở ứng dụng kiểm tra** trên Dashboard. Role Tester mặc định được gán thêm cho Lưu Hoàng Phúc; Admin có thể gán cho tài khoản khác trong Quản lý người dùng.

Màn hình dành cho người dùng hệ thống, tách khỏi phần quản trị: **chuẩn bị mẫu → thu/đọc tín hiệu → kiểm tra mẫu là của ai**. Không yêu cầu nhập người có mùi đó và không chọn vị trí cơ thể.

- **Thu mẫu mới:** chạy thử luồng UI baseline → chờ Expose → exposure → chờ Recover → recovery → xác nhận hoàn tất. Có đồng hồ, trạng thái, hủy, tua từng pha và lượt mới. Chưa mở Serial hoặc điều khiển ESP32; nhãn SIMULATOR luôn hiện rõ. Mẫu `TEST-...` chỉ là ID phiên UI, không sinh raw.csv.
- **Mẫu đã thu:** tìm và chọn lượt thu từ data/, xem tín hiệu gốc rồi bấm **Kiểm tra danh tính** để đọc kết quả prediction.json đã lưu. Không chạy lại model hoặc dùng nhãn mẫu để suy danh tính.
- Kết quả trình bày tên người khớp, similarity/threshold/margin nếu file có; `identity_rejected` hiển thị Unknown; `quality_rejected` yêu cầu thu lại; `ranked_match_only` chưa xác nhận người. Thiếu file hoặc chưa có AI là trạng thái chờ tích hợp riêng, **không phải Unknown**.
- Lịch sử các lần bấm kiểm tra giữ trong component cho phiên màn hình hiện tại; audit thao tác lưu trong trình duyệt. Rời màn hình/refresh sẽ reset phiên thu thử và lịch sử tại đây.
- Tester được xem/chạy kiểm tra, thu thử, xem thư viện chỉ đọc và hồ sơ cá nhân; không quản trị users/roles/models, không sửa/xóa dataset. Researcher xem kiểm tra nhưng không có quyền Control thu thử; Operator và quản trị có thể thao tác theo ma trận quyền.

Để hoàn thành luồng thu **thật** rồi nhận diện **mới**, cần nối gateway trả raw.csv/session và API suy luận model. UI hiện không giả lập người khớp hay score khi hai dịch vụ này chưa tích hợp. Bộ tách trạng thái nằm ở `src/testWorkflow.ts`, màn hình ở `src/pages/Tester.tsx`; kết luận gốc vẫn đọc qua adapter chỉ đọc hiện có.

## Chạy giao diện

Yêu cầu Node.js 22.13+ và npm. Python `.venv` đang bật không ảnh hưởng.

```powershell
cd D:\PBL6\frontend
npm.cmd ci
npm.cmd run dev
```

Mở URL terminal in ra, mặc định `http://127.0.0.1:5173/`. Nếu server đang chạy từ bản cũ, khởi động lại để nạp adapter đọc dữ liệu.

Thư mục cần giữ đúng cấu trúc:

```text
PBL6/
├── data/          # Dữ liệu gốc trên máy, chỉ đọc
└── frontend/      # Code giao diện và adapter đọc cục bộ
```

Adapter tự xác định `../data` từ vị trí mã nguồn, không phụ thuộc shell đang ở thư mục nào. Không cần sao chép data vào `public/`, không cần upload hoặc đưa data lên Git.

```powershell
npm.cmd run build      # TypeScript + Vite production build
npm.cmd run preview    # Xem bản build, vẫn đọc ../data bằng adapter cục bộ
npm.cmd test           # Domain / route render / read-only adapter tests
npm.cmd run check:data # Đọc kiểm tra dataset thật trên máy, không sửa file
npm.cmd run format     # Định dạng source
```

Build không nhúng dữ liệu vào `dist/`. Chỉ upload `dist/` lên hosting tĩnh sẽ không đọc được ổ đĩa trên máy: cần chạy bằng Vite dev/preview cục bộ hoặc tích hợp API riêng sau này. Giữ server ở loopback như cấu hình mặc định.

## Những phần đọc dữ liệu thật

- **Dashboard**: thống kê từ thư mục data, ba hồ sơ nhận diện, mẫu gần đây, biểu đồ thật của lượt thu gần nhất đã ghép nhãn.
- **Hồ sơ nhận diện**: Nguyễn Văn Tài, Nguyễn Văn Dương, Lưu Hoàng Phúc; số lượt thu/ngày; bấm xem lịch sử và biểu đồ từng mẫu.
- **Thư viện mùi cơ thể**: tìm theo nhãn/đường dẫn/người, lọc hồ sơ/ngày/QC, phân trang, chọn 2–5 mẫu để đối chiếu, xuất danh mục metadata JSON.
- **Chi tiết mẫu**: tín hiệu thật, chọn kênh và pha; kiểm tra số dòng, min/max/trung bình và số giá trị hợp lệ; metadata/summary nguyên bản; SHA-256 của raw.csv; bảng pha đo; prediction.json nếu có.
- **AI & nhận diện**: chọn mẫu thật và model dự kiến, xem tín hiệu đầu vào, đọc kết quả prediction.json đã có; target matching cho phép chọn tối đa 5 ứng viên và đối chiếu tín hiệu. Chưa chạy model mới, không sinh score hoặc danh tính giả.
- **Báo cáo thí nghiệm**: số mẫu và nhóm QC từ danh mục gốc, lọc theo ngày có trong dataset, biểu đồ số lượt theo hồ sơ.

Bấm tên mẫu hoặc **Xem biểu đồ** để mở; có deep link `/#/samples?id=DATA-...` và `/#/samples?person=P001`. Biểu đồ dùng đơn vị thực V, Ω, °C, %RH, hPa, không trộn các kênh khác đơn vị vào cùng trục. Di chuột xem thời điểm/pha/giá trị.

## Cơ chế chỉ đọc

`server/dataset.mjs` là adapter đọc file cục bộ được gắn vào Vite dev và preview. Đây chưa phải backend nghiệp vụ hoặc dịch vụ xác thực.

| Endpoint                              | Chức năng                                                            |
| ------------------------------------- | -------------------------------------------------------------------- |
| `GET /api/dataset`                    | Danh mục lượt thu, schema, nhãn, đường dẫn tương đối, kênh và QC gốc |
| `GET /api/dataset?refresh=1`          | Quét lại thư mục data, vẫn chỉ đọc                                   |
| `GET /api/dataset/sample?id=DATA-...` | Raw signal, metadata, summary, prediction, thống kê và SHA-256       |

- Chỉ có GET/HEAD. POST, PUT, PATCH và DELETE bị trả **405**.
- Không có lệnh ghi, đổi tên, xóa hoặc chạy lại pipeline trên dataset.
- Mẫu thật không nằm trong mutable store; không có form sửa QC, metadata hoặc xóa mẫu gốc.
- ID tra từ danh mục server, không nhận đường dẫn file do client gửi. Kiểm tra `realpath` để giới hạn trong data, không đi theo symlink/junction khi quét. Không đi theo trường `source_raw` trong metadata.
- Chỉ đọc `raw.csv` và JSON liên quan trong từng thư mục thu; không mở tùy ý mọi file trên máy.
- Log phiên tổng (`session/raw.csv`, hoặc metadata `kind=session`) không đưa vào danh mục lượt riêng để tránh đếm trùng. Dữ liệu này vẫn nguyên vẹn trên đĩa.
- Thư mục chứa MAT, CSV nghiên cứu bên ngoài không theo cấu trúc raw.csv chưa được nhập vào thư viện này.
- Danh mục cache tối đa 30 giây; dùng **Đọc lại data/** để chủ động quét lại. Mẫu được tải chi tiết khi mở, không gửi toàn bộ dataset sang browser ngay lúc vào.

Không công khai server này ra Internet; đăng nhập hiện vẫn là UI demo và chưa xác thực quyền ở server. Các role chỉ phục vụ xem trước giao diện. Khi tích hợp backend thật cần kiểm tra quyền ở từng API.

## Nhãn danh tính và QC

Ghép hồ sơ bằng **alias đầu nhãn**, giữ nguyên tên file và metadata:

- Tài: `Tai`, `aTai`, `BaseTai`, `TaivsCF`.
- Dương: `Duong`, `aDuong`, `DuongCaphe2`.
- Phúc: `Phuc`, `phucluu`, `luuhoangphuc`, `phucgg`, `phuuc`.

Không dùng tên phòng chứa Tài để gán Tài cho các mẫu khác, không coi `aDung` là Dương. Không gán mẫu không khí/cà phê hoặc tên không rõ vào một trong ba người. Alias chỉ để tổ chức dữ liệu, **không phải kết luận nhận diện AI**; nếu có alias không đúng chủ thể, sửa bảng ánh xạ trong adapter thay vì sửa dữ liệu gốc.

Lần kiểm tra trên dataset hiện tại đọc được 213 lượt riêng, bỏ đếm trùng 74 log phiên: Tài 34, Dương 18, Phúc 47, chưa ghép/đối chứng 114. Các con số sẽ thay đổi khi data có thêm lượt thu.

- `COMPLETE` chỉ mô tả quy trình, không được tự đổi thành QC PASS.
- Giữ `qcSource` gốc. `PASS`/`FAIL` tường minh được giữ; `INSUFFICIENT` hoặc quy trình `ERROR` được phân nhóm FAIL trong UI; `UNCONFIGURED` và trường hợp chưa có kết luận được phân nhóm REVIEW.
- Tín hiệu chart loại các điểm không đạt cờ status/fresh/valid; BME gas thêm gas_valid/heater_stable/new_data. Vẫn giữ khoảng trống, không fill lỗi bằng 0, không làm mượt và không nối qua khoảng cách trên 3 giây.
- Thống kê min/max/mean chỉ dùng giá trị hợp lệ của kênh trong toàn file. Trục thời gian là số giây tính từ timestamp monotonic/elapsed đầu tiên.
- Không thay tên MQ135 cũ thành TGS2602. Hỗ trợ riêng ba schema hiện có: legacy v1, legacy v2 và `robonose.dataset.v1`.

## Phần UI còn mô phỏng

Quản lý user/role/nhóm, lời mời, session, MFA, đổi mật khẩu, API token metadata, system health, cấu hình và audit vẫn là UI localStorage. Không gửi email, không lưu mật khẩu, không có khóa API thật. Model Registry chỉ đăng ký metadata.

Thiết bị và phiên thu mới vẫn là simulator: không mở COM, không bật bơm/van thật, không ghi raw.csv vào data. Quy trình giữ các bước WAIT thủ công:

```text
MONITOR → BASELINE → WAIT_EXPOSURE → EXPOSURE
        → WAIT_RECOVERY → RECOVERY → WAIT_FINISH → WAIT_NAME
        → lưu metadata demo → Next → MONITOR
```

Hồ sơ chưa tự xác nhận đồng ý tham gia. Trước khi tạo phiên mô phỏng, vào hồ sơ người để xác nhận trường đồng ý; trạng thái đó chỉ lưu trên trình duyệt, không khẳng định thay cho tài liệu đồng ý gốc.

## Lưu trữ và cập nhật từ bản UI cũ

- localStorage giữ khóa `robonose.frontend.v1`, payload version **3**; sessionStorage giữ role và trạng thái vào/thoát demo.
- Khi gặp dữ liệu version 1 của giao diện cũ, tự chuyển sang đúng ba user/hồ sơ, bỏ mẫu và lịch sử giả cũ; giữ cấu hình/ma trận quyền hợp lệ. Không đụng đến data trên đĩa.
- Payload version 2 được bổ sung role Tester/module testing, giữ các sửa đổi user, hồ sơ, cấu hình và quyền đã có. Bổ sung role Tester cho tài khoản USR-003. Backup UI version 2 vẫn khôi phục được và được bổ sung ma trận mới; backup xuất mới là version 3.
- Reset hoặc khôi phục backup trong Cài đặt chỉ thay dữ liệu trình duyệt. Backup UI không chứa raw.csv hoặc toàn bộ metadata dataset thật; không khôi phục vào data/.
- Các form/phiên simulator chưa lưu sẽ reset khi rời trang hoặc refresh.

## Cấu trúc code

```text
frontend/
├── server/dataset.mjs             # Adapter chỉ đọc ../data
├── scripts/check-local-data.mjs   # Kiểm tra dataset thật, chỉ đọc
├── src/
│   ├── App.tsx                   # Shell, role preview, hash routes, 403
│   ├── data.ts                   # Đúng ba user/hồ sơ, không có mẫu giả
│   ├── services/dataset.ts       # API catalog/detail và loading/error
│   ├── services/store.ts         # Chỉ dữ liệu UI được phép thay đổi
│   ├── components/DatasetCharts.tsx # SVG tín hiệu thật, pha, thống kê
│   ├── components/ui.tsx         # Thành phần dùng chung, chart simulator
│   ├── pages/Research.tsx        # Thư viện và hồ sơ nhận diện
│   ├── pages/Identity.tsx        # Luồng nhận diện bằng mùi
│   └── pages/                    # Các phân hệ còn lại
└── tests/                        # Domain, render và adapter read-only
```

Font Be Vietnam Pro tải từ Google Fonts, có Segoe UI/sans-serif dự phòng. Chưa có browser khả dụng trong công cụ kiểm tra nên chưa xác nhận bố cục trực quan hoặc click đầu-cuối; tests render phía server không thay thế kiểm tra trình duyệt.

Đã kiểm tra: build production thành công; 18 kiểm thử về quyền, chuyển cấu hình cũ, quy trình thu Tester, phân biệt kết quả nhận diện và render các route. Lần nối dataset trước đã xác nhận API danh mục/chi tiết trả 200; POST/PUT/PATCH/DELETE trả 405; đối chiếu SHA-256 của 808 file dữ liệu gốc không đổi. Bổ sung Tester không thêm endpoint ghi dữ liệu hoặc sửa adapter gốc.

## Tích hợp tiếp

Thay adapter bằng API read-only tương đương nếu muốn triển khai xa máy có data. Tiếp theo nối dịch vụ nhận diện thật: kiểm tra schema/protocol/scaler/model tương thích, đọc tín hiệu thật, trả danh tính hoặc Unknown với score/threshold/margin. Không sử dụng nhãn thư mục làm kết quả model.

Auth/RBAC phải lấy từ server; gateway là owner COM duy nhất; chờ command ACK và MCU state trước khi báo thành công. Không cho reset cấu hình UI hoặc backup ghi vào data gốc. Chưa có multi-organization, custom role CRUD, upload avatar, SMTP, model binary import hoặc backup dataset thật.

## Đưa lên Git

Chỉ source frontend cần commit. `node_modules/`, `dist/`, `.checks/` và `*.tsbuildinfo` đã được ignore. Không đưa dataset lên Git.

```powershell
cd D:\PBL6
git add frontend/
git diff --cached --stat
git commit -m "feat: connect read-only odor dataset and identity profiles"
```

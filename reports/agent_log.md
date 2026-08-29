# Nhật Ký Quyết Định Cùng AI Coding Agent (AI Agent Decision Log)

Không cần sao chép toàn bộ hội thoại. Ghi lại các quyết định kỹ thuật và bằng chứng quan trọng.

## Quyết Định 1: Thực Thi Data Contract Xác Định & Phân Cấp Mức Độ Nghiêm Trọng (Severity)
- **Giả thuyết (Hypothesis)**: Trôi dạt kiểu dữ liệu (type drift) và dữ liệu cũ (stale data) âm thầm làm sai lệch các bảng mart phía downstream mà không gây lỗi cú pháp SQL; contract cần phải bắt buộc kiểm tra kiểu dữ liệu một cách xác định, đo lường độ tươi (freshness), và kích hoạt hành động cách ly (quarantine) dựa trên mức độ nghiêm trọng.
- **Yêu cầu đối với AI Agent**: Nâng cấp bộ validator kiểm tra kiểu dữ liệu, kiểm tra độ tươi và thiết lập Checkpoint Great Expectations với cơ chế phân loại cảnh báo.
- **Đề xuất của AI Agent**: Mở rộng `src/contract_validator.py` với tính năng ép kiểu và kiểm tra đa kiểu (`integer`, `number`, `datetime`, `string`, `boolean`) cùng phép đo độ trễ `delay_minutes` so với UTC. Nâng cấp `gx/validate_orders.py` lên chuẩn GX 1.21 `ExpectationSuite` + `Checkpoint` kích hoạt `QUARANTINE / BLOCK` khi có lỗi critical.
- **Bằng chứng/Kiểm thử**: Chạy `inject.bat duplicate_pk` dẫn đến `critical_contract_fails: 1` trong baseline và `Overall Result: FAIL -> [ACTION REQUIRED] QUARANTINE / BLOCK PIPELINE` trong GX. Toàn bộ 12 test public ban đầu đều PASS.
- **Quyết định (Accept / Reject / Revise)**: Chấp nhận (Accept).
- **Lý do**: Cung cấp lớp lọc ingress vững chắc trước khi nạp dữ liệu vào dbt và ngăn chặn dữ liệu bẩn xâm nhập kho dữ liệu (+10 điểm).

## Quyết Định 2: dbt Native Unit Testing & Bảo Vệ Khỏi Hiện Tượng Fanout Phép Join
- **Giả thuyết (Hypothesis)**: Khi các bảng chiều (ví dụ: SCD Type 2 `stg_customers`) chứa nhiều bản ghi active cho cùng một thực thể, phép join thông thường sẽ nhân bản các dòng fact và thổi phồng doanh thu một cách giả tạo mà không phát sinh lỗi SQL.
- **Yêu cầu đối với AI Agent**: Viết dbt native unit test tái hiện lỗi thổi phồng doanh thu và bảo vệ mô hình khỏi hiện tượng trùng lặp bản ghi chiều.
- **Đề xuất của AI Agent**: Tạo file `dbt_project/models/marts/unit_tests.yml` với các unit test chuẩn dbt (`completed_orders_sum_to_expected_revenue` và `duplicate_active_customers_do_not_inflate_revenue`). Trong `fct_daily_revenue.sql`, áp dụng `distinct customer_id` cho CTE `active_customers` và `count(distinct o.order_id)` trước khi tổng hợp.
- **Bằng chứng/Kiểm thử**: Lệnh `dbt.bat` chạy thành công 18/18 tác vụ (14 models/data tests + 2 unit tests + 2 seeds). Cả 2 unit test đều vượt qua, chứng minh mô hình hoàn toàn miễn nhiễm với lỗi nhân bản khách hàng.
- **Quyết định (Accept / Reject / Revise)**: Chấp nhận (Accept).
- **Lý do**: Đảm bảo tính chính xác tuyệt đối của số liệu doanh thu và đáp ứng tiêu chí dbt native unit test (+3 điểm bonus).

## Quyết Định 3: Phát Hiện Bất Thường Thống Kê Robust & Độ Lệch Phân Phối (Distribution Drift)
- **Giả thuyết (Hypothesis)**: Các ngưỡng cố định viết cứng (ví dụ: `row_count == 600`) gây báo động giả vào cuối tuần và bỏ sót các sự cố trích xuất thiếu một phần dữ liệu. Bộ phát hiện MAD mạnh mẽ kết hợp ngữ cảnh và kiểm định thống kê KS 2 mẫu có thể phân biệt chính xác bất thường thực sự với biến động tự nhiên.
- **Yêu cầu đối với AI Agent**: Nâng cấp `observability/anomaly.py` và `observability/distribution.py` để xử lý trường hợp MAD=0, nhận diện ngữ cảnh phân khúc, và tích hợp kiểm định Kolmogorov-Smirnov.
- **Đề xuất của AI Agent**: Cài đặt `mad_detector` với cơ chế fallback sang độ lệch tuyệt đối trung bình (mean absolute deviation) khi MAD=0; nâng cấp `detect_anomaly(method='auto')` tận dụng `same_segment_history` và `known_event`; tích hợp `scipy.stats.ks_2samp` vào `detect_distribution_shift`.
- **Bằng chứng/Kiểm thử**: `inject.bat volume_drop` (150/600 dòng) vượt qua toàn bộ kiểm tra schema contract nhưng bị bắt chính xác bởi `auto:mad` với điểm bất thường 5.53 (vượt ngưỡng 3.0). Toàn bộ pytest suites đều PASS.
- **Quyết định (Accept / Reject / Revise)**: Chấp nhận (Accept).
- **Lý do**: Mang lại khả năng quan sát thống kê cho các đợt sụt giảm thể tích dữ liệu không lường trước và trôi dạt phân phối (+3 điểm bonus).

## Quyết Định 4: Truy Vết Lineage & Phạm Vi Ảnh Hưởng Cấp Cột (Transitive Column Lineage)
- **Giả thuyết (Hypothesis)**: Lineage cha-con trực tiếp không thể truy vết được tác động bắc cầu (transitive) qua nhiều tầng mart và dashboard. Đồ thị cần duyệt theo thuật toán BFS hoàn chỉnh để xác định toàn bộ bán kính ảnh hưởng.
- **Yêu cầu đối với AI Agent**: Triển khai thuật toán duyệt lineage cấp cột bắc cầu trong `observability/lineage.py`.
- **Đề xuất của AI Agent**: Thay thế phép tra cứu từ điển trực tiếp trong `get_column_downstream` bằng thuật toán duyệt hàng đợi BFS có tập `seen` chống lặp chu trình.
- **Bằng chứng/Kiểm thử**: Test `test_transitive_column_lineage` xác nhận `orders.amount` truyền ảnh hưởng xuyên suốt qua `stg_orders.amount_usd` -> `fct_daily_revenue.daily_revenue` -> `ceo_dashboard.total_rev`. Tất cả test lineage đều PASS.
- **Quyết định (Accept / Reject / Revise)**: Chấp nhận (Accept).
- **Lý do**: Định vị chính xác phạm vi ảnh hưởng khi đổi tên cột, đổi kiểu dữ liệu, hoặc sai lệch công thức (+7 điểm bonus).

## Quyết Định 5: Cảnh Báo Tốc Độ Tiêu Hao Budget Đa Cửa Sổ (Multi-Window Burn-Rate) & Giám Sát RAG
- **Giả thuyết (Hypothesis)**: Cảnh báo error budget đơn cửa sổ gây báo động giả quá mức khi có các đợt spike ngắn thoáng qua. Đánh giá đồng thời cả cửa sổ ngắn (1h) và cửa sổ dài (6h) đảm bảo chỉ phát chuông báo động trang khi ngân sách lỗi thực sự bị cạn kiệt liên tục.
- **Yêu cầu đối với AI Agent**: Cài đặt chính sách cảnh báo Multi-Window Burn Rate theo chuẩn Google SRE và phát hiện trôi dạt chuẩn vector embedding RAG.
- **Đề xuất của AI Agent**: Cài đặt `evaluate_multiwindow_burn` kiểm tra `short_window_burn >= 14.4 và long_window_burn >= 14.4` để phát cảnh báo trang (Page), đồng thời hạ cấp spike ngắn (`long_window_burn < 14.4`) thành cảnh báo không làm phiền (Warning). Cài đặt `detect_embedding_norm_shift` trong `observability/rag_metrics.py`.
- **Bằng chứng/Kiểm thử**: `test_multiwindow_sustained_fast_burn_pages` xác nhận `page=True, severity="critical"`; `test_multiwindow_transient_spike_does_not_page` xác nhận `page=False, severity="warning"`. Toàn bộ 16 public tests đều PASS.
- **Quyết định (Accept / Reject / Revise)**: Chấp nhận (Accept).
- **Lý do**: Tuân thủ tiêu chuẩn vận hành tin cậy Google SRE, chống mỏi cảnh báo (alert fatigue), và quan sát trôi dạt embedding (+7 điểm bonus).



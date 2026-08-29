# Báo Cáo Sự Cố (Incident Report) — Data & AI Reliability Game Day

## Mức độ nghiêm trọng (Severity)
**P1 — Cảnh báo nghiêm trọng về chất lượng dữ liệu & Báo cáo doanh thu**

## Tóm tắt sự cố (Summary)
Sự kết hợp giữa lỗi trùng lặp khóa chính đầu nguồn (duplicate PK), mất mát dữ liệu một phần trong quá trình ETL (giảm 75% volume), hiện tượng nhân bản bản ghi do join chiều khách hàng SCD Type 2, và tài liệu Knowledge Base bị trễ cập nhật (stale data) đã đe dọa trực tiếp đến tính chính xác của doanh thu trên Dashboard CEO và khiến Agent hỗ trợ khách hàng trả về chính sách hoàn tiền đã hết hạn.

## Phát hiện sự cố (Detection)
- **Tín hiệu 1 (Dữ liệu đầu vào - Ingress)**: Bộ kiểm tra Data Contract kích hoạt lỗi `critical` do vi phạm `unique: order_id`. Great Expectations checkpoint lập tức chặn pipeline và kích hoạt hành động `QUARANTINE / BLOCK`.
- **Tín hiệu 2 (Khối lượng dữ liệu - Volume)**: Bộ phát hiện bất thường thống kê robust MAD phát hiện số lượng đơn hàng giảm đột ngột xuống 150 dòng (điểm số: `5.53`, ngưỡng: `3.0`), bắt được sự cố suy giảm dữ liệu âm thầm dù pipeline SQL vẫn báo `SUCCESS`.
- **Tín hiệu 3 (Biến đổi dữ liệu - Transformation)**: dbt native unit test phát hiện doanh thu bị thổi phồng do bảng khách hàng SCD chứa nhiều bản ghi active đồng thời.
- **Tín hiệu 4 (Hệ tri thức - Knowledge Base)**: Bộ kiểm tra Freshness Contract phát hiện mốc thời gian `published_at` bị trễ quá ngưỡng SLO cho phép (60 phút).
- **Thời gian ghi nhận đầu tiên**: 2026-08-29 08:30 UTC

## Nguyên nhân gốc rễ (Root Cause)
1. **Dữ liệu Order đầu nguồn**: Dịch vụ ingestion retry gửi lại các lô dữ liệu mà không có cơ chế khử trùng lặp (deduplication), dẫn đến việc xuất hiện các bản ghi trùng `order_id`.
2. **Join bảng chiều SCD Type 2**: Bảng `stg_customers` chứa các khoảng thời gian hiệu lực bị chồng lấn (`is_active = true`), khiến thao tác `LEFT JOIN` nhân bản các dòng order trong mart `fct_daily_revenue`.
3. **Lỗi một phần trong luồng ETL**: Stream ingestion bị cắt ngắn dữ liệu nhưng không ném ra mã lỗi khác 0, khiến hệ thống hiểu nhầm là đã chạy thành công.
4. **Cơ sở tri thức RAG**: Tiến trình tự động đồng bộ tài liệu chính sách bị treo, khiến tài liệu cũ vẫn tồn tại trong vector database.

## Bằng chứng kỹ thuật (Evidence)
1. **Kiểm tra Ingress Contract**: `contract failed checks: 1` với vi phạm `unique: order_id` (`severity: critical`).
2. **Great Expectations Suite**: `orders_suite` thất bại tại expectation `ExpectColumnValuesToBeUnique(order_id)`.
3. **Quan sát thống kê (Observability)**: `detect_metric(150, history, method="auto")` trả về `is_anomaly=True, score=5.53, method=auto:mad`.
4. **dbt Unit Test**: Unit test `duplicate_active_customers_do_not_inflate_revenue` phát hiện sai lệch trước khi bổ sung ràng buộc khóa định danh.
5. **Kiểm tra Freshness**: `kb_failed_contract_checks: 1` với `delay_minutes > 60`.

## Phạm vi ảnh hưởng (Blast Radius)

```text
[stg_orders] & [stg_customers]
   │
   ▼
[fct_daily_revenue]
   │
   ▼
[ceo_revenue_dashboard] (Chỉ số tài chính, Doanh thu ngày, Quyết định điều hành)

[kb_documents]
   │
   ▼
[active_kb / Vector DB]
   │
   ▼
[support_rag_agent] (Chính sách hoàn tiền, Tự động xử lý ticket hỗ trợ)
```

## Giải pháp khắc phục (Mitigation)
1. **Cách ly dữ liệu đầu vào (Quarantine)**: Áp dụng cơ chế chặn hợp đồng dữ liệu (Contract validation) ngay trước khi dbt nạp dữ liệu vào warehouse.
2. **Bảo vệ phép Join trong Mart**: Tái cấu trúc mô hình `fct_daily_revenue.sql` với `distinct customer_id` và `count(distinct o.order_id)` nhằm đảm bảo lực lượng quan hệ 1-1.
3. **Cảnh báo bất thường thống kê**: Triển khai bộ phát hiện MAD có nhận biết ngữ cảnh (Context-aware) và tính chu kỳ theo ngày trong tuần (Day-of-Week).
4. **Giám sát độ tươi (Freshness) & SLO**: Kích hoạt cơ chế cảnh báo Multi-Window Burn Rate (báo động trang khi tốc độ tiêu hao ngân sách nhanh >= 14.4x, triệt tiêu các cảnh báo tức thời vô hại).

## Khôi phục hệ thống (Recovery)
- Chạy lại luồng thu nạp dữ liệu qua đường ống kiểm duyệt contract.
- Thực thi script `scripts/reset_lab.py` để đưa dữ liệu về baseline chuẩn.
- Chạy `dbt build` tái tạo toàn bộ mart `fct_daily_revenue` với 18/18 test vượt qua thành công.

## Xác nhận khôi phục (Verification)
- [x] Data Contract đạt chuẩn (`orders_contract.yaml` & `kb_contract.yaml` 0 lỗi)
- [x] dbt tests hoàn thành (11 data tests + 2 unit tests + 3 models pass)
- [x] Phân phối & số lượng trở về ngưỡng bình thường (khớp với baseline lịch sử)
- [x] SLO ổn định / Error budget trong tầm kiểm soát (burn rate < 1.0, còn 100% budget)
- [x] Dữ liệu downstream được đối soát (tổng doanh thu trên dashboard khớp với tổng giá trị các đơn completed)

## Kế hoạch phòng ngừa sự cố (Action Items)
| Hành động | Phụ trách | Hạn chót | Lý do |
|---|---|---|---|
| Áp dụng Data Contract chặn lỗi trong CI/CD & Airflow | Data Platform Team | 2026-09-05 | Chặn schema lỗi trước khi đi vào Data Warehouse |
| Chuẩn hóa dbt Native Unit Tests cho tất cả các phép join SCD | Analytics Engineering | 2026-09-08 | Tránh hiện tượng fanout làm sai lệch số liệu doanh thu |
| Triển khai cảnh báo Google SRE Multi-Window Burn Rate | SRE / Reliability | 2026-09-10 | Cảnh báo kịp thời khi cạn budget, tránh mỏi cảnh báo (alert fatigue) |
| Thiết lập kiểm tra nhịp tim (Heartbeat) độ tươi cho KB | AI / Support Eng | 2026-09-12 | Đảm bảo bot AI không phục vụ chính sách đã hết hạn |



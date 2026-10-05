# BÁO CÁO VIÊN — KHÔNG DÙNG LLM

## ⚠️ Bạn KHÔNG dùng mô hình ngôn ngữ

Bạn là một chương trình Python thuần, dùng Jinja2 để điền dữ liệu vào
template HTML.

**Lý do:** nếu để mô hình ngôn ngữ sinh HTML trực tiếp thì CSS sẽ hỏng,
thiếu thẻ, bảng vỡ layout — và người dùng phải tự sửa tay. Template tĩnh
đảm bảo HTML luôn đẹp và không bao giờ vỡ, bất kể model có mạnh đến đâu.

## Việc của bạn

1. Nhận dữ liệu từ trạng thái của hệ thống (kết quả build, test, code
   đã đổi, quyết định thiết kế).
2. Điền vào `templates/design.html.j2` hoặc `templates/report.html.j2`.
3. Ghi ra file HTML trong thư mục project.

## Hai tài liệu khác nhau

| File | Khi nào | Nội dung |
|---|---|---|
| `design.html` | Sau khi các tác tử thống nhất thiết kế | kiến trúc, quyết định, design token, điểm phản biện |
| `report.html` | Sau khi xong dự án | tiến độ, thay đổi code, kết quả test, CI/CD |

## Quy tắc dữ liệu

- **Số liệu phải đến từ máy.** Ví dụ "38 test pass" lấy từ output của
  Gradle, không phải từ lời agent tự nhận.
- **Dữ liệu thiếu thì để trống**, đừng bịa số liệu để cho đẹp. Một báo
  cáo trống chỗ còn tốt hơn một báo cáo bịa.
- **Escape dữ liệu trước khi chèn** vào HTML — tên file, mô tả lỗi do
  model sinh ra có thể chứa ký tự `<`, `>`.

## Không được làm

- Không tự sinh nội dung mô tả, nhận xét hay kết luận
- Không gọi network
- Không viết lại template — template là nguồn sự thật về giao diện

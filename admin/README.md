# Máy chủ bản quyền Reup Voice Studio

Gói này dành riêng cho quản trị; không đưa vào bộ cài khách hàng.
Đọc README.md ở gốc repo; bộ phận này tùy chọn, không cần cho bản cộng đồng MIT.
Chạy `pip install -r requirements.txt`, đặt REUP_LICENSE_HOME tới nơi lưu bí mật và DB.
Khởi tạo `python LICENSE_SERVER.py init`. Sao lưu signing.key, giữ kín file này;
chỉ public_key được đóng kèm bộ cài. `create --days 365 --seats 1` tạo key mới.
`serve --port 18880` chạy localhost; dùng nginx.example.conf làm mẫu reverse proxy HTTPS.
Không dùng domain example hoặc file chứng chỉ mẫu làm cấu hình sản xuất.
TLS, domain/VPS, quản lý dịch vụ tự khởi động và monitoring do bạn triển khai.
Chưa có trang web quản trị: cấp/thu hồi/reset máy bằng CLI tại máy chủ.
DB chỉ lưu hash key, mã máy hash và thời hạn/số máy. Tránh log request body.
Lease có chữ ký hết hạn sau tối đa 24 giờ; client mới gia hạn nền bằng phiên bảo vệ DPAPI.
Máy chủ không cấp key qua HTTP, chỉ xác thực key đã tạo bằng CLI.
Không có tài khoản/mật khẩu mặc định hay khóa bí mật trong gói này.

## Gia hạn nền (10/10/2026)

Cập nhật cả LICENSE_SERVER.py và nginx.example.conf để mở `/v1/refresh` qua HTTPS.
Client cũ vẫn kích hoạt như trước; server cũ không cấp phiên mới nên cần nhập key lại.
Client mới yêu cầu phiên khi kích hoạt: DB chỉ lưu hash token, client chỉ lưu token đã
mã hóa Windows DPAPI, gắn với máy/URL/public key. Không lưu activation key.
Gia hạn trước khi lease còn 6 giờ; lỗi mạng giữ lease chưa hết hạn và retry có backoff.
Phiên có hạn tối đa 30 ngày không hoạt động, không vượt hạn key. Thu hồi key/reset máy
chặn lần gia hạn tiếp theo; máy offline vẫn dùng lease đã cấp đến khi hết hạn (tối đa 24 giờ).
Không log request body/token. Sao lưu DB và signing.key bằng cơ chế riêng bảo mật.
Chưa triển khai server/domain thật hoặc GUI quản trị trong lượt này.

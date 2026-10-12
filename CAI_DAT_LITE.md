# Reup Voice Studio 0.5.1 Lite — bản dùng tạm

Windows 10/11 x64. Chạy setup, chọn thư mục, mở shortcut Reup Voice Studio.
Không cần tự cài Python; shortcut chạy ReupVoiceStudio.exe có logo.
Đóng ứng dụng trước khi nâng cấp. Không xóa bản cũ/dữ liệu trước khi kiểm tra bản mới.

## Cài thư viện sau

Setup chỉ có giao diện, Python, FFmpeg và các thư viện media cơ bản, không có
runtime/model VieNeu, Whisper, Kokoro, Qwen3, Chatterbox, VSR, Demucs, căn lời hoặc tách nền.
Mở ⚙ Cài đặt → Thư viện tùy chọn, chọn thư mục thư viện, bấm Tải/cài đúng bộ cần dùng.
Các bộ cài xong và qua kiểm tra sẽ tự kết nối. Không tải AI chỉ vì mở app/chọn tab.
Cài thư viện cần Internet và nhiều GB dung lượng tùy bộ; CPU chạy các bộ lớn rất chậm.
VieNeu tải theo FP32/INT8 đang chọn; Whisper tải model đang chọn trong Cài đặt.
Nếu đổi precision/model sau đó, cần cài bộ tương ứng trước khi chạy offline.

## Dữ liệu và bảo mật

Dữ liệu mới tại %LOCALAPPDATA%\ReupVoiceStudio; vị trí thư viện/đầu ra có thể đổi.
Không đưa dự án, lịch sử, key API hay dữ liệu cá nhân của máy phát triển vào setup.
Nếu chuyển máy, sao lưu dữ liệu riêng; setup không chứa dữ liệu này.
Setup chưa ký Authenticode, chưa mã hóa/obfuscate Python/JavaScript. SHA-256 chỉ để
đối chiếu file. Auto-update và bắt buộc bản quyền chưa bật trong bản dùng tạm.
Đọc THIRD_PARTY_NOTICES.md và DEPENDENCIES.json về thành phần bên thứ ba.

Đây là bản thử nghiệm, chưa nghiệm thu trên Windows sạch.

# ReupStudio / Reup Voice Studio

**Free, open-source, local-first video and voice studio.** Mã nguồn miễn phí dưới
giấy phép MIT, dành cho cộng đồng sử dụng, sửa đổi và đóng góp.

Windows 10/11 x64 · Python 3.11 · UI: Tiếng Việt / English / 简体中文.
Phiên bản mã nguồn hiện tại: **0.5.1**. Đây là bản cộng đồng đang phát triển,
không phải bản cam kết đã nghiệm thu trên mọi máy.

## Chức năng

- Văn bản → giọng nói, voice clone, đọc tài liệu và hội thoại/podcast đa ngôn ngữ.
- Lồng tiếng video, nhận dạng Whisper, dịch qua API LLM do bạn cấu hình,
  chỉnh cue và tốc độ đọc, phụ đề và tiêu đề.
- Biên tập timeline nhiều lớp, chữ/phụ đề, hiệu ứng, keyframe, phối lớp local
  hoặc đề xuất bằng prompt LLM có bước duyệt/Hoàn tác.
- Tải video/audio qua yt-dlp và xóa logo/phụ đề từ ảnh/video, xử lý hàng loạt.
- Thư viện AI cài/gỡ theo yêu cầu; quản lý đầu ra, lịch sử và sao lưu/khôi phục.

## Cài từ mã nguồn (Windows)

1. Cài **Python 3.11 x64** (có Python Launcher) và Git.
2. Clone repo và cài core:

```powershell
git clone https://github.com/bitgacon/reupstudio.git
cd reupstudio
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-core.txt
```

Cũng có thể chạy `INSTALL_CORE.bat`. Core không cài Torch/Whisper/TTS/model AI.

3. Cài **FFmpeg và ffprobe** từ nguồn phù hợp, đặt cả hai vào PATH hoặc vào
   `tools/ffmpeg.exe` và `tools/ffprobe.exe`. Kiểm tra `ffmpeg -version` và
   `ffprobe -version`. Repo không đóng kèm binary FFmpeg.
4. Chạy:

```powershell
.\.venv\Scripts\python.exe run.py
# Nếu không dùng cửa sổ Qt:
.\.venv\Scripts\python.exe run.py --browser
```

Hoặc dùng `MO_REUP_VOICE_STUDIO.bat` / `MO_BANG_TRINH_DUYET.bat`.
Mở **Cài đặt → Thư viện** để cài bộ TTS/Whisper/VSR cần dùng. Không tự tải model
khi mở app; cài AI có thể cần nhiều GB. Chưa cài TTS thì chưa tạo được giọng.
Không cần MoneyPrinterTurbo hoặc mua key để dùng bản cộng đồng.

## English quick start

Install Python 3.11 x64 and FFmpeg/ffprobe, create `.venv`, install
`requirements-core.txt`, then run `.venv\Scripts\python.exe run.py`.
Use `--browser` for the browser UI. Optional TTS, ASR and AI libraries/models are
installed on demand in Settings → Libraries, not bundled in this repository.
Your LLM/TTS provider may charge for API use; software being free does not make
third-party services or model licenses free of restrictions.

## Dữ liệu, quyền riêng tư và an toàn

Source checkout mặc định lưu tại `data/` (đã gitignore). Có thể đặt `REUP_DATA`
để chọn nơi khác. Dữ liệu không được đưa vào repo; hãy sao lưu trước nâng cấp.
API key có thể được lưu trong settings cục bộ: không chia sẻ `data`, cookies,
voice samples, file backup chứa key hoặc ảnh log chưa che thông tin riêng.
Không expose server localhost ra Internet; ứng dụng không phải dịch vụ multi-user.
Dịch/director/cloud TTS chỉ gửi dữ liệu theo lựa chọn và quyền cho phép của bạn.
Chỉ dùng media/giọng/chân dung có quyền sử dụng; không vượt DRM hoặc giả mạo người khác.

## Giới hạn hiện tại

CPU có thể chậm với Qwen3/Omni/VSR; MuseTalk cần NVIDIA và nghiệm thu trên GPU thật.
Forced alignment và ReID đã tích hợp nhưng chất lượng model/audio/video thật cần
kiểm thử thêm. Director chỉ đề xuất lớp mới tối đa 60s từ prompt/metadata, không
phân tích cảnh phim hay tự dựng cả phim. Avatar nhiều người nói tự động chưa có.
Không có server bản quyền/update sản xuất được cấu hình trong bản cộng đồng.
Các adapter quản trị/phát hành nằm trong `admin/`, hoàn toàn tùy chọn.

## Giấy phép

Mã ReupStudio: **MIT**, xem [LICENSE](LICENSE). Giữ attribution MIT của phần kế
thừa MoneyPrinterTurbo trong [LICENSE-MPT.txt](LICENSE-MPT.txt).
MIT không thay thế giấy phép tài nguyên và dependencies: Be Vietnam Pro là OFL,
Twemoji là CC BY 4.0, Fluent Emoji có MIT riêng; FFmpeg/Qt và model tải ngoài giữ
giấy phép của chính chúng. Xem [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Đặc biệt kiểm tra điều kiện thương mại của model alignment/TTS/avatar trước dùng.

## Đóng góp và kiểm thử

Xem [CONTRIBUTING.md](CONTRIBUTING.md). Dùng dữ liệu tổng hợp khi gửi lỗi/PR;
không upload video, giọng, API key hoặc project riêng.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
node --test tests/*.cjs
```

Một số test cần FFmpeg hoặc runtime tùy chọn; runtime/model thực tế cần nghiệm thu
riêng. Hướng dẫn tính năng nằm trong các file `HUONG_DAN_*.md`; các tài liệu Lite
đề cập bộ cài cũ không phải hướng dẫn cài source và không kèm installer ở repo này.

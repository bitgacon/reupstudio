# Nguồn và thành phần

## Bản cài Lite 0.5.1 dùng tạm

Chỉ kèm Python, Qt/PySide6 và thư viện GUI/media (phiên bản thực tế trong
DEPENDENCIES.json), FFmpeg/ffprobe 8.0.1 essentials_build từ gyan.dev.
FFmpeg này báo GPLv3 hoặc mới hơn, không phải bản LGPL-only. Xem
tools/COPYING.GPLv3, tools/BUILD-AND-LICENSE.txt; nguồn FFmpeg:
https://github.com/FFmpeg/FFmpeg/tree/n8.0.1 và nhà cung cấp binary:
https://www.gyan.dev/ffmpeg/builds/. PySide6/Qt giữ các file license trong runtime;
nguồn/giấy phép upstream: https://doc.qt.io/qtforpython-6/licenses.html.
Không hạn chế việc thay các DLL Qt đi kèm bằng bản tương thích; launcher không
kiểm tra/chặn thay DLL. Bộ cài không có runtime/model AI, API key hay dữ liệu cá nhân.
Đây không phải kết luận nghiệm thu pháp lý cho phát hành thương mại rộng rãi;
cần rà soát nguồn tương ứng và nghĩa vụ của cả các dependency native trước khi phát hành.

- Downloader dùng yt-dlp: https://github.com/yt-dlp/yt-dlp — source Python theo Unlicense; dependencies và binary build có giấy phép riêng. Module cùng phụ thuộc cài trong runtime source; chưa đóng gói bộ nhị phân mới. Các trang có điều khoản truy cập/bản quyền riêng; không vượt DRM.

- Giao diện Reup Voice Studio được viết mới theo bố cục tham khảo người dùng gửi; không dùng tên/logo hoặc mã nguồn CIT Voice Studio. Đây không phải sản phẩm được CIT chứng nhận.
- Thuật toán đọc DOCX/SRT, cắt lặng, căn audio theo cue được điều chỉnh từ MoneyPrinterTurbo / MPT Omni Studio trong workspace. Giữ giấy phép MIT của MoneyPrinterTurbo tại `LICENSE-MPT.txt`.
- VieNeu-TTS: https://github.com/pnnbao97/VieNeu-TTS — dùng API của package cục bộ, không sao chép model vào mã nguồn nhánh này. Model/cache/runtime giữ giấy phép từ bộ cài của chúng.
- FastAPI, Uvicorn, requests, pydub, pypdf, faster-whisper và CTranslate2 dùng theo các giấy phép tương ứng trong môi trường Python.
- PySide6/Qt WebEngine và FFmpeg/ffprobe là runtime bên ngoài. Việc phát hành nhị phân cần giữ license/notices và thực hiện nghĩa vụ giấy phép của đúng bản build; bản FFmpeg của bộ MPT có thể thuộc GPL.
- Font Be Vietnam Pro lấy từ tài nguyên MPT; SIL Open Font License. Xem `OFL-BeVietnamPro.txt` và nguồn https://github.com/google/fonts/tree/main/ofl/bevietnampro.
- Tách giọng tùy chọn: Demucs 4.0.1 (MIT), https://github.com/facebookresearch/demucs; model htdemucs tải từ kho upstream theo bộ nạp Demucs. PyTorch/Torchaudio 2.5.1 CPU và các phụ thuộc được cài riêng trong `separation-env`; giữ license trong môi trường khi phân phối. Gói source không chứa thư viện hoặc model này. Kho Demucs upstream đã chuyển trạng thái archive; chức năng được pin phiên bản và đã test trên PC hiện tại, không cam kết tương thích mọi bản Python mới.

Bản mã nguồn hiện không phải bộ nhị phân công khai đã rà soát giấy phép phát hành. Không gửi API key, Project hay giọng riêng khi chia sẻ mã.

- Kết nối ngoài VSR: https://github.com/YaoFANGUK/video-subtitle-remover (repository Apache-2.0). Adapter Reup tự viết gọi CLI `backend/main.py`; không sao chép/đóng kèm code, binary, model, GUI hoặc dependencies VSR. Các model/STTN/LaMa/ProPainter/Paddle/Torch/GUI dependencies có giấy phép/điều kiện riêng, cần rà soát khi định phân phối bộ runtime. Hỗ trợ OCR lấy hard-sub (VSE) chưa được tích hợp. Kết nối ngoài không phải kết luận giấy phép cho một gói phân phối chung.

- Adapter dịch 0.3 viết riêng bằng requests/HTMLParser, đối chiếu giao thức Google V1 từ https://github.com/SubtitleEdit/subtitleedit/blob/main/src/libuilogic/AutoTranslate/GoogleTranslateV1.cs và Google Web từ https://github.com/nidhaloff/deep-translator/blob/master/deep_translator/google.py. Không đóng kèm hay chạy Subtitle Edit/deep-translator. Dịch vụ Google có điều khoản/hạn mức riêng; không phải cam kết dịch vụ Google Cloud V2 và không được Google chứng nhận.
- TDTStudio chỉ được đọc cấu trúc thư mục và tham khảo ảnh giao diện do người dùng cung cấp. Không trích mã chương trình, tài nguyên thương hiệu, model hay thư viện từ bộ TDTStudio vào gói Reup.

- AI hình tùy chọn: OpenCV 4.12.0 (Apache-2.0), Haar cascade đi kèm package giữ notice/giấy phép dữ liệu upstream; rembg 2.0.67 (MIT), U2NetP tải theo rembg từ dự án U-2-Net (Apache-2.0). Nguồn https://github.com/opencv/opencv, https://github.com/danielgatis/rembg, https://github.com/xuebinqin/U-2-Net. Môi trường vision-env riêng gồm ONNX Runtime và các phụ thuộc với giấy phép riêng; giữ đầy đủ notices khi phân phối nhị phân. Chưa rà soát nghĩa vụ bản phát hành cuối.
- QA hình dùng ảnh NASA astronaut đi kèm scikit-image (https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut), chỉ trong kho QA, không lấy ảnh/video người dùng.

- Kho sáng tạo: 12 đồ họa Twemoji © Twitter, Inc and contributors, pin v14.0.2, CC BY 4.0. Nguồn https://github.com/twitter/twemoji/tree/v14.0.2/assets/svg; bản SVG được rasterize thành PNG 512px. Giữ web/creative/TWEMOJI-LICENSE.txt và thông tin ghi công; cần attribution thích hợp khi xuất/đăng video dùng nhãn dán. Editor tạo ATTRIBUTION.txt cạnh video để người dùng giữ và ghi nguồn. Hiệu ứng particle/ring/confetti là đồ họa thủ tục riêng của Reup, không lấy từ CapCut. PREPARE_CREATIVE.py chỉ dùng endpoint upstream cố định, không tải từ URL tùy ý.
- Fluent Emoji: 24 tài nguyên (12 emoji, mỗi emoji có 3D PNG và Flat SVG rasterized PNG), Microsoft Corporation, MIT License, pin commit 1ffb34c752ecf5d402f04cfb4b392c77f57c54bc. Nguồn https://github.com/microsoft/fluentui-emoji. Giữ toàn bộ web/creative/FLUENT-LICENSE.txt; attribution của asset chứa bản MIT notice đầy đủ, được xuất trong ATTRIBUTION.txt. 3D giữ độ phân giải nguồn, không gọi là asset 4K. Tám lớp hologram/aurora/doodle/speed/bokeh/rain/snow/orbit là đồ họa thủ tục riêng, không sao chép shader hay artwork của thư viện khác.
# Public source / bản cộng đồng MIT

MIT trong LICENSE áp dụng cho mã ReupStudio, không thay thế giấy phép của font,
emoji, dependencies hoặc model bên ngoài. Public repo không kèm binary/runtime,
trọng số model, API key hay dữ liệu người dùng. Các mô tả Lite/binary ở dưới là
notice lịch sử của bộ cài, không có nghĩa các binary đó nằm trong public repo.


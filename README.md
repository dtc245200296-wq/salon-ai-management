# Hệ thống quản lý đặt lịch salon tóc có tích hợp AI

## Công nghệ
- Flask + Jinja2
- SQLite
- Google Gemini (tùy chọn)
- Google Search grounding qua Gemini khi có quota/API
- DDGS web-search fallback khi Gemini không khả dụng
- HTML/CSS/JavaScript

## Chạy
```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe app.py
```
Mở `http://127.0.0.1:5000`

## Demo
- Admin: `admin / 123456`
- Lễ tân: `le_tan / 123456`
- Thợ: `tho01 / 123456`

## AI
1. Gợi ý dịch vụ dựa trên nhu cầu, lịch sử khách và danh sách dịch vụ.
2. Sinh tin nhắn chăm sóc khách hàng.
3. Tóm tắt lịch sử khách hàng.
4. Chatbot salon; câu hỏi về pháp luật/thông tin cập nhật có thể dùng Google Search qua Gemini. Nếu Gemini không khả dụng hoặc hết quota, hệ thống dùng DDGS để tìm kiếm web và trả nguồn.

## Bảo mật
- Mật khẩu lưu hash.
- API key chỉ đặt trong `.env`, không commit.
- AI chỉ được phép đề xuất dịch vụ tồn tại trong danh mục được cấp.

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Nạp biến môi trường từ file .env
load_dotenv()

# ============================================================
# Gemini SDK mới: google-genai
# ============================================================
use_new_sdk = False
try:
    from google import genai
    from google.genai import types
    use_new_sdk = True
except Exception:
    genai = None
    types = None

# ============================================================
# Gemini SDK cũ: google-generativeai (fallback)
# ============================================================
legacy_genai = None
if not use_new_sdk:
    try:
        import google.generativeai as legacy_genai
    except Exception:
        legacy_genai = None

# ============================================================
# DuckDuckGo Search fallback
# ============================================================
try:
    from ddgs import DDGS
except Exception:
    DDGS = None


BASE_DIR = Path(__file__).resolve().parent
SERVICES_DIR = BASE_DIR / "data" / "services"

# Số lần thử lại khi Gemini trả lỗi tạm thời.
MAX_RETRIES = 2
RETRY_DELAYS = (1.5, 3.0)

# Model fallback chỉ được dùng khi lỗi là lỗi tạm thời như 503/429.
# gemini-3.6-flash vẫn là model mặc định theo .env của bạn.
DEFAULT_FALLBACK_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
]


def _service_text(services):
    return "\n".join(
        f"- {s['name']} | {s.get('category', '')} | "
        f"{s.get('duration_minutes', 0)} phút | "
        f"{float(s.get('price', 0)):,.0f} VNĐ | "
        f"{s.get('description', '')}"
        for s in services
    ) or "Chưa có dịch vụ nào."


def _history_text(history):
    return "\n".join(
        f"- {h.get('appointment_date', '')}: "
        f"{h.get('service_name', '')} | "
        f"kiểu: {h.get('hair_style', '')} | "
        f"màu: {h.get('hair_color', '')} | "
        f"ghi chú: {h.get('customer_note', '')} | "
        f"kết quả: {h.get('result', '')}"
        for h in history
    ) or "Chưa có lịch sử dịch vụ."


def _parse_json(text, fallback):
    """Parse JSON kể cả khi model bọc JSON trong ```json ... ``` ."""
    if not text:
        return fallback

    cleaned = text.strip()

    # Bỏ markdown code fence nếu có.
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Tìm object JSON đầu tiên trong nội dung.
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return fallback

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return fallback


def _normalize_model(raw_model):
    """Chuẩn hóa tên model nhưng không tự ý đổi model hợp lệ do người dùng cấu hình."""
    model = (raw_model or "").strip()
    model = model.replace("models/", "").replace('"', "").replace("'", "").strip()
    return model or "gemini-3.6-flash"


def _model_candidates(use_search=False):
    env_name = "GEMINI_WEB_MODEL" if use_search else "GEMINI_MODEL"
    primary = _normalize_model(os.getenv(env_name, "gemini-3.6-flash"))

    # Cho phép người dùng tự định nghĩa fallback trong .env.
    raw_fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", "")
    if raw_fallbacks:
        configured = [
            _normalize_model(item)
            for item in raw_fallbacks.split(",")
            if item.strip()
        ]
    else:
        configured = DEFAULT_FALLBACK_MODELS

    candidates = []
    for model in [primary, *configured]:
        if model and model not in candidates:
            candidates.append(model)
    return candidates


def _is_transient_gemini_error(exc):
    """503/429/quá tải là lỗi có thể thử lại hoặc chuyển model."""
    message = str(exc).upper()
    transient_markers = (
        "503",
        "UNAVAILABLE",
        "429",
        "RESOURCE_EXHAUSTED",
        "TOO MANY REQUESTS",
        "HIGH DEMAND",
        "OVERLOADED",
        "RATE LIMIT",
        "TRY AGAIN LATER",
        "INTERNAL SERVER ERROR",
        "500",
    )
    return any(marker in message for marker in transient_markers)


def _extract_grounding_sources(result):
    sources = []

    # Một số phiên bản SDK đặt grounding_metadata ở response,
    # một số trường hợp truy cập được thông qua candidate.
    grounding = getattr(result, "grounding_metadata", None)

    if grounding is None:
        candidates = getattr(result, "candidates", None) or []
        if candidates:
            grounding = getattr(candidates[0], "grounding_metadata", None)

    if grounding:
        chunks = getattr(grounding, "grounding_chunks", None) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if not web:
                continue

            uri = getattr(web, "uri", None)
            title = getattr(web, "title", None)
            if uri:
                sources.append({
                    "title": title or uri,
                    "url": uri,
                })

    # Loại trùng URL.
    unique = []
    seen = set()
    for item in sources:
        url = item.get("url")
        if url and url not in seen:
            seen.add(url)
            unique.append(item)
    return unique


def _generate_with_new_sdk(client, model, prompt, use_search=False, system_instruction=None):
    config_args = {}

    if system_instruction and types:
        config_args["system_instruction"] = system_instruction

    if use_search and types:
        # Google Search grounding theo SDK google-genai mới.
        config_args["tools"] = [
            types.Tool(google_search=types.GoogleSearch())
        ]

    config = types.GenerateContentConfig(**config_args) if config_args else None

    if config:
        return client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )

    return client.models.generate_content(
        model=model,
        contents=prompt,
    )


def _gemini_text(prompt, use_search=False, system_instruction=None):
    """
    Gọi Gemini với:
    - retry khi 503/429;
    - tự chuyển model khi model hiện tại đang quá tải;
    - giữ thông báo lỗi cụ thể thay vì luôn bảo người dùng kiểm tra API key.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return None, "Lỗi: Không tìm thấy GEMINI_API_KEY trong file .env", []

    models = _model_candidates(use_search=use_search)
    last_error = None

    # --------------------------------------------------------
    # SDK mới
    # --------------------------------------------------------
    if use_new_sdk and genai:
        try:
            client = genai.Client(api_key=api_key)
        except Exception as exc:
            return None, f"Lỗi khởi tạo Gemini SDK: {exc}", []

        for model_index, model in enumerate(models):
            for attempt in range(MAX_RETRIES + 1):
                try:
                    result = _generate_with_new_sdk(
                        client=client,
                        model=model,
                        prompt=prompt,
                        use_search=use_search,
                        system_instruction=system_instruction,
                    )

                    text = (getattr(result, "text", None) or "").strip()
                    sources = _extract_grounding_sources(result)

                    if text:
                        # mode vẫn là gemini; nếu dùng fallback model thì ghi rõ.
                        mode = "gemini" if model_index == 0 else f"gemini_fallback:{model}"
                        return text, mode, sources

                    last_error = "Gemini trả về phản hồi rỗng."
                    break

                except Exception as exc:
                    last_error = str(exc)

                    # Lỗi không mang tính tạm thời: không thử vô ích.
                    if not _is_transient_gemini_error(exc):
                        return None, f"Lỗi Gemini (SDK mới, model {model}): {exc}", []

                    # Còn lượt retry -> chờ rồi thử lại cùng model.
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
                        continue

                    # Hết retry -> chuyển model kế tiếp.
                    break

        return None, (
            "Lỗi Gemini: các model hiện được cấu hình đều đang tạm thời quá tải "
            f"hoặc không khả dụng. Chi tiết cuối: {last_error}"
        ), []

    # --------------------------------------------------------
    # SDK cũ: chỉ dùng nếu máy chưa có google-genai
    # --------------------------------------------------------
    if legacy_genai:
        try:
            legacy_genai.configure(api_key=api_key)

            for model_index, model in enumerate(models):
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        kwargs = {"model_name": model}
                        if system_instruction:
                            kwargs["system_instruction"] = system_instruction

                        gen_model = legacy_genai.GenerativeModel(**kwargs)
                        res = gen_model.generate_content(prompt)
                        text = (getattr(res, "text", None) or "").strip()

                        if text:
                            mode = "gemini_legacy" if model_index == 0 else f"gemini_legacy_fallback:{model}"
                            return text, mode, []

                        last_error = "Gemini trả về phản hồi rỗng."
                        break

                    except Exception as exc:
                        last_error = str(exc)
                        if not _is_transient_gemini_error(exc):
                            return None, f"Lỗi Gemini (SDK cũ, model {model}): {exc}", []

                        if attempt < MAX_RETRIES:
                            time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
                            continue
                        break

            return None, (
                "Lỗi Gemini: các model hiện được cấu hình đều đang tạm thời quá tải "
                f"hoặc không khả dụng. Chi tiết cuối: {last_error}"
            ), []

        except Exception as exc:
            return None, f"Lỗi Gemini (SDK cũ): {exc}", []

    return None, (
        "Lỗi: Chưa cài thư viện google-genai hoặc google-generativeai trong môi trường Python"
    ), []


def _web_fallback(query):
    if DDGS is None:
        return None, "ddgs_unavailable", []

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

        if not results:
            return None, "no_web_results", []

        lines = ["Kết quả tìm kiếm Internet:", ""]
        sources = []

        for i, item in enumerate(results, 1):
            title = item.get("title") or item.get("href") or f"Nguồn {i}"
            href = item.get("href") or item.get("url") or ""
            body = item.get("body") or item.get("snippet") or ""
            lines.append(f"{i}. {title}\n{body}\n{href}\n")

            if href:
                sources.append({"title": title, "url": href})

        return "\n".join(lines).strip(), "web_fallback", sources

    except Exception as exc:
        return None, f"web_error:{exc}", []


def _is_web_question(message):
    keywords = [
        "luật lao động",
        "pháp luật",
        "quy định mới",
        "quy định hiện hành",
        "năm 2026",
        "hiện nay",
        "mới nhất",
        "theo luật",
        "internet",
        "trên mạng",
    ]
    m = message.lower()
    return any(k in m for k in keywords)


def recommend_service(customer, history, services):
    prompt = f"""Bạn là trợ lý tư vấn salon tóc. Chỉ được đề xuất dịch vụ tồn tại trong danh sách.
KHÁCH HÀNG: {customer['full_name']}; ghi chú: {customer.get('note', '')}
LỊCH SỬ:
{_history_text(history)}
DỊCH VỤ HIỆN CÓ:
{_service_text(services)}
Trả về JSON gồm recommended_services, reason, warning."""

    text, mode, _ = _gemini_text(prompt, use_search=False)

    fallback = {
        "recommended_services": [s["name"] for s in services[:2]],
        "reason": "Gợi ý dựa trên danh sách dịch vụ hiện tại.",
        "warning": "Nhân viên nên kiểm tra thực tế tóc trước khi thực hiện.",
        "mode": "rule_fallback",
    }

    result = _parse_json(text, fallback) if text else fallback
    result["mode"] = mode
    return result


def generate_message(customer, history, services):
    prompt = f"""Viết một tin nhắn chăm sóc khách hàng ngắn, lịch sự cho salon tóc.
Khách: {customer['full_name']}
Lịch sử:
{_history_text(history)}
Dịch vụ:
{_service_text(services)}"""

    text, mode, _ = _gemini_text(prompt)
    reply = text or f"Chào {customer['full_name']}, salon rất vui được phục vụ bạn."
    return {"reply": reply, "mode": mode}


def summarize_customer(customer, history):
    prompt = f"""Tóm tắt lịch sử khách hàng salon trong 3-5 câu.
Khách: {customer['full_name']}
Lịch sử:
{_history_text(history)}"""

    text, mode, _ = _gemini_text(prompt)
    return {
        "summary": text or "Chưa có đủ lịch sử để tóm tắt.",
        "mode": mode,
    }


def chat_salon(message, context):
    services = context.get("services", [])

    # 1. Tra cứu Internet nếu là câu hỏi luật/cập nhật.
    if _is_web_question(message):
        prompt = f"Trả lời câu hỏi bằng tiếng Việt: {message}"
        text, mode, sources = _gemini_text(
            prompt,
            use_search=True,
        )

        if text:
            return {
                "reply": text,
                "mode": mode,
                "sources": sources,
                "citations": sources,
            }

        fallback, fallback_mode, fallback_sources = _web_fallback(message)
        if fallback:
            return {
                "reply": fallback,
                "mode": fallback_mode,
                "sources": fallback_sources,
                "citations": fallback_sources,
            }

        return {
            "reply": (
                "⚠️ Hiện chưa thể kết nối AI hoặc tra cứu Internet. "
                f"Chi tiết: {mode}"
            ),
            "mode": "web_unavailable",
            "sources": [],
            "citations": [],
        }

    # 2. Tư vấn Master Stylist chuyên sâu.
    system_instruction = """
Bạn là Master Stylist & Trợ lý Chuyên gia của Salon Tóc.
Nhiệm vụ của bạn là tư vấn kỹ thuật, màu nhuộm, kiểu tóc CHI TIẾT, ĐẦY ĐỦ và CHUYÊN SÂU nhất.

Khi tư vấn làm tóc/nhuộm tóc:
1. 🔍 Kỹ thuật & Đặc điểm tóc: phân tích độ dài, vị trí sát da đầu (nhiệt da đầu làm màu lên nhanh hơn), nền tóc mặc định là tóc đen tự nhiên.
2. 🎨 Bảng màu gợi ý chi tiết:
   - Nhóm không tẩy (Nâu socola, Nâu hạt dẻ, Xanh đen...).
   - Nhóm nâng nền (Nâu khói, Nâu rêu, Nâu tây...).
   - Nhóm tẩy/fashion (Bạch kim, Xám khói, Tím pastel...).
3. 💡 Tư vấn theo Tone da: da ngăm vs da sáng.
4. 🧴 Chăm sóc & Gội sấy: dầu gội giữ màu/dầu gội tím, lưu ý gội sấy.
5. 💇‍♂️ Gợi ý dịch vụ: khéo léo nhắc tới các gói dịch vụ có trong danh sách của Salon.
""".strip()

    prompt = (
        f"DANH SÁCH DỊCH VỤ SALON:\n{_service_text(services)}"
        f"\n\nCÂU HỎI KHÁCH HÀNG:\n{message}"
    )

    text, mode, sources = _gemini_text(
        prompt,
        use_search=False,
        system_instruction=system_instruction,
    )

    if text:
        return {
            "reply": text,
            "mode": mode,
            "sources": sources,
            "citations": sources,
        }

    # Không còn nói “hãy kiểm tra API key” cho mọi lỗi.
    # API key sai chỉ là MỘT trong nhiều khả năng.
    return {
        "reply": (
            "⚠️ **Hệ thống chưa kết nối được AI**\n\n"
            f"{mode}\n\n"
            "Nếu lỗi là 503/429, hệ thống đã tự thử lại và chuyển sang model dự phòng. "
            "Bạn có thể thử gửi lại sau ít phút."
        ),
        "mode": mode,
        "sources": [],
        "citations": [],
    }

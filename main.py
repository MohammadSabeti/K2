import os
import bcrypt
import jdatetime
import streamlit as st
import pandas as pd
import pathlib
from datetime import datetime, timezone
import random
import base64
import streamlit.components.v1 as components
import time
import re
import html
import streamlit as st
import psycopg2
from supabase import create_client

url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["service_key"]
supabase = create_client(url, key)

# --------------------------
# مسیرهای پروژه
# --------------------------
DATA_DIR = pathlib.Path("data")
# DB_FILE = DATA_DIR / "k2.db"
FONTS_DIR = pathlib.Path("fonts")
IMAGES_DIR = pathlib.Path("images")
DATA_DIR.mkdir(exist_ok=True)
FONTS_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)


# --------------------------
# ایجاد جداول SQLite
# --------------------------
def get_connection():
    return psycopg2.connect(st.secrets["postgres"]["url"])

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # جدول کاربران
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP NOT NULL
);
""")

    # # جدول فعالیت‌ها
    # cursor.execute(
    #     """
    #     CREATE TABLE IF NOT EXISTS user_activities (
    #         id INTEGER PRIMARY KEY AUTOINCREMENT,
    #         username TEXT NOT NULL,
    #         week_start TEXT NOT NULL,
    #         week_end TEXT NOT NULL,
    #         name TEXT NOT NULL,
    #         target INTEGER NOT NULL,
    #         done INTEGER NOT NULL,
    #         percent INTEGER NOT NULL,
    #         note TEXT,
    #         saved_at TEXT NOT NULL,
    #         week_feedback TEXT,
    #         week_total_score INTEGER NOT NULL,
    #         progress_diff INTEGER DEFAULT 0
    #     )
    # """
    # )
    # جدول فعالیت‌ها
    cursor.execute(
        """
CREATE TABLE IF NOT EXISTS user_activities (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    name TEXT NOT NULL,
    target INTEGER NOT NULL,
    done INTEGER NOT NULL,
    percent INTEGER NOT NULL,
    note TEXT,
    saved_at TIMESTAMP NOT NULL,
    week_feedback TEXT,
    week_total_score INTEGER NOT NULL,
    progress_diff INTEGER DEFAULT 0
);
    """
    )

    conn.commit()
    conn.close()


# init_db()


# --------------------------
# تابع sanitize نام کاربری
# --------------------------
def sanitize_username(username: str) -> str:
    """حذف کاراکترهای غیرمجاز و محدود کردن طول"""
    # فقط حروف فارسی، انگلیسی، اعداد، فاصله، نقطه، خط‌تیره و زیرخط مجاز است
    clean = re.sub(r"[^a-zA-Z0-9\u0600-\u06FF\s._-]", "", username).strip()
    return clean[:50] or "anonymous"  # حداکثر 50 کاراکتر


def get_admin_cred():
    """
    بارگذاری اطلاعات ادمین از st.secrets یا متغیر محیطی.
    این تابع نام کاربری و رمز (به صورت خام/plain) را بازمی‌گرداند.
    اگر چیزی پیدا نشد، (None, None) باز می‌کند.
    """
    # 1) از st.secrets (Streamlit Cloud یا .streamlit/secrets.toml)
    try:
        if "admin" in st.secrets:
            admin_cfg = st.secrets["admin"]
            usr = admin_cfg.get("username")
            pw = admin_cfg.get("password")  # توجه: اینجا رمز خام انتظار می‌رود
            if usr and pw is not None:
                return usr, pw
    except Exception:
        # در صورتی که st.secrets در محیط فعلی دردسترس نیست، بیخیال می‌شویم و به fallback می‌رویم
        pass

    # 2) fallback به متغیر محیطی (در صورت نیاز)
    usr = os.environ.get("K2_ADMIN_USERNAME")
    pw = os.environ.get("K2_ADMIN_PASSWORD")  # رمز خام از env
    if usr and pw is not None:
        return usr, pw

    # 3) اگر هیچ‌کدام نبود، None برگردان
    return None, None

# --------------------------
# هش ایمن رمز عبور
# --------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))


# --------------------------
# توابع مدیریت کاربر
# --------------------------
def get_user(username: str):
    res = supabase.table("users").select("*").eq("username", username).execute()
    if res.data:
        user = res.data[0]
        return {
            "username": user["username"],
            "password_hash": user["password_hash"],
            "role": user["role"]
        }
    return None


def create_user(username: str, password: str, role: str = "user"):
    try:
        password_hash = hash_password(password)
        created_at = datetime.now(timezone.utc).isoformat()

        supabase.table("users").insert({
            "username": username,
            "password_hash": password_hash,
            "role": role,
            "created_at": created_at
        }).execute()

        return True
    except Exception as e:
        timed_message('error',f"❌ خطا در ایجاد کاربر: {e}")
        return False


def change_password(username: str, new_password: str):
    new_hash = hash_password(new_password)
    supabase.table("users").update({"password_hash": new_hash}).eq("username", username).execute()


# --------------------------
# توابع کمکی
# --------------------------

def jalali_to_gregorian(jalali_str: str) -> str:
    """تبدیل تاریخ شمسی به میلادی برای sorting"""
    try:
        y, m, d = map(int, jalali_str.split('/'))
        g_date = jdatetime.date(y, m, d).togregorian()
        return g_date.isoformat()
    except:
        return jalali_str


def timed_message(msg_type: str, message: str, duration: int = 10, position="inline"):
    """نمایش یک پیام موقت و استایل‌دهی‌شده در برنامه Streamlit.

    این تابع یک بنر پیام موقت را با استفاده از HTML، CSS و JavaScript در محیط Streamlit
    تولید و نمایش می‌دهد. پیام به‌صورت انیمیشنی ظاهر شده، برای مدت زمان مشخصی نمایش داده می‌شود
    و سپس به‌صورت خودکار محو و حذف می‌گردد. نوع پیام می‌تواند موفقیت، اطلاع، خطا یا هشدار باشد
    که هر کدام رنگ و آیکون مخصوص خود را دارند.

    Args:
        msg_type (str): نوع پیام برای نمایش. مقادیر مجاز عبارت‌اند از:
            - "success": پیام موفقیت با رنگ سبز و آیکون تیک.
            - "info": پیام اطلاع‌رسانی با رنگ آبی و آیکون ℹ️.
            - "error": پیام خطا با رنگ قرمز و آیکون ❌.
            - "warning": پیام هشدار با رنگ زرد و آیکون ⚠️.
            اگر مقدار نامعتبر داده شود، مقدار پیش‌فرض "info" استفاده می‌شود.
        message (str): محتوای متنی پیام که باید نمایش داده شود.
        duration (int, اختیاری): مدت زمان نمایش پیام (بر حسب ثانیه) قبل از محو شدن خودکار.
            مقدار پیش‌فرض برابر ۱۰ ثانیه است.
        position (str, اختیاری): محل نمایش بنر در صفحه. مقادیر مجاز:
            - "top": در بالای صفحه و به‌صورت ثابت نمایش داده می‌شود.
            - "inline": در جریان معمول محتوای صفحه قرار می‌گیرد.
            مقدار پیش‌فرض "inline" است.

    Raises:
        NameError: در صورتی که متغیر `font_b64` در محدوده فعلی تعریف نشده باشد.

    نکات:
        - این تابع به متغیر سراسری `font_b64` برای فونت Base64 نیاز دارد.
        - برای نمایش HTML سفارشی از `streamlit.components.v1.html` استفاده می‌کند.
        - طراحی آن واکنش‌گرا بوده و در دستگاه‌های موبایل نیز به‌درستی نمایش داده می‌شود.
    """
    colors = {
        "success": {
            "bg": "rgba(16, 185, 129, 0.15)",
            "border": "rgba(16, 185, 129, 0.8)",
            "text": "#a7f3d0",
            "icon": "✅",
        },
        "info": {
            "bg": "rgba(59, 130, 246, 0.15)",
            "border": "rgba(59, 130, 246, 0.8)",
            "text": "#bfdbfe",
            "icon": "ℹ️",
        },
        "error": {
            "bg": "rgba(239, 68, 68, 0.15)",
            "border": "rgba(239, 68, 68, 0.8)",
            "text": "#fecaca",
            "icon": "❌",
        },
        "warning": {
            "bg": "rgba(245, 158, 11, 0.15)",
            "border": "rgba(245, 158, 11, 0.8)",
            "text": "#fde68a",
            "icon": "⚠️",
        },
    }
    c = colors.get(msg_type, colors["info"])

    container_style = (
        "position:fixed;top:20px;left:0;width:100%;z-index:9999;display:flex;justify-content:center;"
        if position == "top"
        else "width:100%;margin-top:10px;display:flex;justify-content:center;"
    )

    html = f"""
    <style>
    @font-face {{
    font-family: 'Vazir-Medium';
    src: url(data:font/ttf;base64,{font_b64}) format('truetype');
    font-weight: normal;
    font-style: normal;
}}

@keyframes fadeIn {{
    0% {{ opacity: 0; transform: translateY(-15px) scale(0.98); }}
    100% {{ opacity: 1; transform: translateY(0) scale(1); }}
}}

@keyframes fadeOut {{
    0% {{ opacity: 1; transform: translateY(0) scale(1); }}
    100% {{ opacity: 0; transform: translateY(-15px) scale(0.98); }}
}}

#custom-banner > div {{
    direction: rtl;
    backdrop-filter: blur(10px) saturate(180%);
    -webkit-backdrop-filter: blur(10px) saturate(180%);
    background:{{c['bg']}};
    border:1px solid {{c['border']}};
    color:{{c['text']}};
    font-family:'Vazir-Medium', sans-serif;
    font-weight:500;
    font-size:16px;
    padding:16px 24px;
    border-radius:14px;
    box-shadow:0 8px 24px rgba(0,0,0,0.4);
    display:flex;
    justify-content:center;
    align-items:center;
    gap:12px;
    animation: fadeIn 0.5s ease-in-out;
    transition: all 0.5s ease-in-out;
    width: 80%;
    max-width: 600px;
}}

@media (max-width: 768px) {{
    #custom-banner > div {{
        width: 90vw;
        font-size: 14px;
        padding: 12px 16px;
        gap: 8px;
    }}
    #custom-banner > div span:first-child {{
        font-size: 20px;
    }}
}}

@media (max-width: 480px) {{
    #custom-banner > div {{
        width: 95vw;
        font-size: 13px;
        padding: 10px 12px;
        gap: 6px;
    }}
    #custom-banner > div span:first-child {{
        font-size: 18px;
    }}
}}
    </style>

    <div id="custom-banner" style="{container_style}">
        <div style="
            direction: rtl;
            backdrop-filter: blur(10px) saturate(180%);
            -webkit-backdrop-filter: blur(10px) saturate(180%);
            background:{c['bg']};
            border:1px solid {c['border']};
            color:{c['text']};
            font-family:'Vazir-Medium', sans-serif;
            font-weight:500;
            font-size:16px;
            padding:16px 24px;
            border-radius:14px;
            box-shadow:0 8px 24px rgba(0,0,0,0.4);
            display:flex;
            justify-content:center;
            align-items:center;
            gap:12px;
            animation: fadeIn 0.5s ease-in-out;
            transition: all 0.5s ease-in-out;
            max-width: 600px;
            width: 80%;
        ">
            <span style="font-size:22px;">{c['icon']}</span>
            <span style="flex:1;">{message}</span>
        </div>
    </div>

    <script>
        const banner = document.getElementById('custom-banner');
        if (banner) {{
            setTimeout(() => {{
                banner.firstElementChild.style.animation = 'fadeOut 0.5s ease-in-out forwards';
                setTimeout(() => banner.remove(), 600);
            }}, {duration * 1000});
        }}
    </script>
    """
    components.html(html, height=100)


def motivational_message(percent: int) -> str:
    """بازگرداندن یک پیام انگیزشی بر اساس درصد پیشرفت.

    این تابع بر اساس درصد پیشرفت ورودی، یک پیام انگیزشی تصادفی بازمی‌گرداند.
    پیام‌ها برای محدوده‌های مختلف پیشرفت طراحی شده‌اند تا انگیزه و حس موفقیت
    کاربر را تقویت کنند. این پیام‌ها شامل آیکون‌ها و متن کوتاه و مثبت هستند.

    Args:
        percent (int): درصد پیشرفت یا تکمیل یک کار (۰ تا بالای ۱۰۰).
            بر اساس این مقدار، پیام مناسب انتخاب می‌شود:
            - 100 یا بالاتر: پیام‌های حداکثر موفقیت.
            - 80 تا 99: پیام‌های نزدیک به هدف.
            - 50 تا 79: پیام‌های پیشرفت متوسط.
            - 30 تا 49: پیام‌های تشویقی برای شروع و ادامه.
            - کمتر از 30: پیام‌های انگیزشی برای ادامه تلاش.

    Returns:
        str: یک پیام انگیزشی تصادفی متناسب با درصد ورودی.

    Notes:
        - تابع از ماژول `random` برای انتخاب پیام تصادفی استفاده می‌کند.
        - پیام‌های بازگشتی شامل آیکون‌ها و متن کوتاه هستند تا تاثیرگذاری بیشتری داشته باشند.
        - درصد ورودی می‌تواند عددی بالاتر از 100 باشد که در این صورت پیام‌های موفقیت کامل انتخاب می‌شوند.
    """

    if percent >= 100:
        return random.choice(
            [
                "🏆 فوق‌العاده! به قله رسیدی — افتخار کن به خودت!",
                "🎉 عالی! تمام تلاش‌ها نتیجه داد، به خودت افتخار کن!",
                "🌟 کامل کردی — مسیرت الهام‌بخشِ!",
                "⛰️ به اوج رسیدی! هر قدمت داستانی از پشتکار داره.",
                "🏅 پیروزیِ تو فقط پایان نیست، آغاز الهام برای دیگرانه.",
                "💎 تو نشون دادی که صبر و تلاش، جواهر ارزشمنده.",
                "⚡ هر موفقیت، نتیجه‌ی هزاران تلاش خاموشه.",
                "🌄 تو نه تنها به هدف رسیدی، بلکه مسیر رو روشن کردی.",
                "🔥 انرژی و پشتکار تو، مسیر دیگران رو هم روشن می‌کنه.",
                "🌈 هر گامی که برداشتی، رنگین‌کمان امید ساخته."
            ]
        )
    if 90 > percent >= 80:
        return random.choice(
            [
                "🌄 عالیه! تقریباً به هدف رسیدی، با انرژی ادامه بده!",
                "🔥 نزدیک قله‌ای — فقط چند قدم دیگه مونده!",
                "💪 عملکرد قوی؛ همین روال رو حفظ کن!",
                "🗻 هر قدمت توی این مسیر، قله‌ی بزرگتری برات می‌سازه.",
                "🌟 مسیر روشنه؛ با هر نفس، به موفقیت نزدیک‌تر می‌شی.",
                "⚡ انرژی مثبتت باعث می‌شه مسیر سخت هم لذت‌بخش بشه.",
                "💡 تقریباً اونجایی که می‌خوای، تمرکز رو از دست نده.",
                "🌱 رشدت محسوسه، ادامه بده که به اوج می‌رسی.",
                "🏞️ هر تلاش کوچیک، قله‌ی بعدی رو نزدیک‌تر می‌کنه.",
                "✨ حتی فاصله‌های کوتاه، نتیجه‌ی بزرگی می‌سازن."
            ]
        )
    if 80 > percent >= 50:
        return random.choice(
            [
                "🔥 داری پیشرفت می‌کنی! فقط چند قدم دیگه تا قله مونده.",
                "✅ خوبه؛ ثبات رو نگه دار تا بهتر بشه.",
                "👏 نتیجهٔ تلاشته — ادامه بده!",
                "🌱 هر قدم کوچیک، ریشه‌ی موفقیت رو محکم‌تر می‌کنه.",
                "⛰️ حتی مسیر سخت، تجربه و قدرت بهت اضافه می‌کنه.",
                "💡 با هر حرکت، مهارت و اعتماد به نفست رشد می‌کنه.",
                "🌄 نترس از سختی؛ کوه‌ها برای فتح ساخته شدن.",
                "✨ صبر و تلاش، چراغ راهت هستن.",
                "💪 پیشرفت تدریجی، پایه‌ی موفقیت بزرگه.",
                "🌿 مسیرت در حال شکل‌گیریه، ادامه بده."
            ]
        )
    if 50 > percent >= 30:
        return random.choice(
            [
                "💡 شروع کردی، ادامه بده! مسیر تازه آغاز شده.",
                "🛠 یک قدم برداشتی؛ برنامه‌ریزی کوچیک کمک می‌کنه.",
                "✨ تلاش رو ادامه بده، نتایج آرام آرام میان.",
                "🌄 حتی کوه بلند هم با اولین قدم شروع می‌شه.",
                "🌱 کاشتن امروز، برداشت فردا — صبور باش.",
                "🔥 هر تلاش، شعله‌ای از امید و پیشرفت روشن می‌کنه.",
                "⚡ مسیر سخت می‌تونه تو رو قوی‌تر کنه، نترس!",
                "🏞️ هر روز یک قدم، روزی مسیر رو کامل می‌کنه.",
                "🌟 با حرکت مداوم، قله دوردست نزدیک می‌شه.",
                "💪 هر پیشرفت کوچک، نشان قدرت اراده‌ت هست."
            ]
        )
    return random.choice(
        [
            "❤️‍🔥 ناامید نشو، فقط یک گام دیگه لازمه!",
            "✊ کوچک شروع کن؛ هر حرکت باارزشه.",
            "🌱 امروز کاشتیم، فردا برداشت می‌کنیم.",
            "⛰️ کوه بزرگ به آرامی فتح می‌شه؛ قدم‌ها کوچک ولی مستمر باشن.",
            "💫 مسیر سخته ولی هر تلاش، تو رو قوی‌تر می‌کنه.",
            "🌟 هیچ شروع کوچکی بی‌اثر نیست؛ ادامه بده!",
            "🔥 امیدت رو نگه دار، هر گامی که برداری مهمه.",
            "🌄 مسیر پرچالشه اما نتیجه شگفت‌انگیزه.",
            "💡 با هر تلاش، شعله‌ی موفقیت روشن می‌شه.",
            "🏞️ امروز سختی داری، فردا قدرت داری."
        ]
    )


def validate_jalali_date(text: str) -> bool:
    """اعتبارسنجی یک رشته به‌عنوان تاریخ شمسی (جلالی).

        این تابع بررسی می‌کند که آیا رشته ورودی نمایانگر یک تاریخ معتبر
        در تقویم جلالی است یا خیر. فرمت ورودی باید به صورت "YYYY/MM/DD" باشد.

        Args:
            text (str): رشته تاریخ مورد نظر برای اعتبارسنجی.
                می‌تواند شامل فاصله در ابتدا و انتها باشد که حذف خواهد شد.

        Returns:
            bool:
                - True اگر رشته یک تاریخ معتبر جلالی باشد.
                - False در غیر این صورت (فرمت اشتباه یا تاریخ نامعتبر).

        Example:
            >>> validate_jalali_date("1402/07/15")
            True
            >>> validate_jalali_date("1402/13/01")
            False

        Notes:
            - تابع از ماژول `jdatetime` برای بررسی اعتبار تاریخ استفاده می‌کند.
            - رشته باید با "/" جدا شده و شامل سال، ماه و روز باشد.
            - مقادیر غیرمجاز یا فرمت اشتباه به False منجر می‌شوند.
        """

    try:
        text = text.strip()
        parts = text.split("/")
        if len(parts) != 3:
            return False
        y, m, d = map(int, parts)
        jdatetime.date(y, m, d)  # این خط خطا می‌دهد اگر تاریخ نامعتبر باشد
        return True
    except (ValueError, OverflowError):
        return False


# --------------------------
# توابع فعالیت‌ها
# --------------------------
def append_user_history(
        username: str,
        activities: list,
        week_start: str,
        week_end: str,
        week_feedback: str,
        week_total_score: int,
):
    """افزودن سوابق هفتگی یک کاربر به پایگاه داده.

    این تابع تمامی فعالیت‌های ارائه‌شده برای یک کاربر را در جدول
    `user_activities` پایگاه داده ذخیره می‌کند. علاوه بر اطلاعات فعالیت،
    بازخورد هفتگی و امتیاز کل هفته نیز ذخیره می‌شوند.

    Args:
        username (str): نام کاربری که سوابق برای آن ثبت می‌شود.
        activities (list): لیستی از دیکشنری‌ها که هر کدام نماینده یک فعالیت هستند.
            هر دیکشنری باید شامل کلیدهای زیر باشد:
            - "name": نام فعالیت
            - "target": هدف فعالیت
            - "done": میزان انجام شده
            - "percent": درصد پیشرفت
            - "note": یادداشت مرتبط با فعالیت
            - "saved_at": تاریخ و زمان ذخیره فعالیت
            - "progress_diff" (اختیاری): تغییر پیشرفت نسبت به هفته قبل
        week_start (str): تاریخ شروع هفته (به صورت رشته).
        week_end (str): تاریخ پایان هفته (به صورت رشته).
        week_feedback (str): بازخورد کلی هفته برای کاربر.
        week_total_score (int): امتیاز کل هفته. اگر None باشد، صفر در نظر گرفته می‌شود.

    Returns:
        None

    Example:
        >>> append_user_history(
        ...     "ali",
        ...     [{"name": "تمرین روزانه", "target": 5, "done": 5, "percent": 100, "note": "", "saved_at": "2025-10-18"}],
        ...     "2025-10-12",
        ...     "2025-10-18",
        ...     "هفته خوبی بود",
        ...     90
        ... )

    Notes:

        - اگر کلید "progress_diff" در دیکشنری فعالیت وجود نداشته باشد، مقدار پیش‌فرض ۰ در نظر گرفته می‌شود.
        - تابع پس از ثبت تمامی فعالیت‌ها، تغییرات را در پایگاه داده اعمال و اتصال را می‌بندد.
    """

    if week_total_score is None:
        week_total_score = 0

    for act in activities:
        supabase.table("user_activities").insert({
            "username": username,
            "week_start": week_start,
            "week_end": week_end,
            "name": act["name"],
            "target": act["target"],
            "done": act["done"],
            "percent": act["percent"],
            "note": act["note"],
            "saved_at": act["saved_at"],
            "week_feedback": week_feedback or "",
            "week_total_score": week_total_score,
            "progress_diff": int(act.get("progress_diff", 0) or 0),
        }).execute()


def load_user_history(username: str) -> pd.DataFrame:
    """بارگذاری سوابق هفتگی یک کاربر از پایگاه داده.

    این تابع تمامی فعالیت‌ها و سوابق هفتگی یک کاربر مشخص را از جدول
    `user_activities` در پایگاه داده استخراج کرده و به صورت یک DataFrame
    از کتابخانه pandas بازمی‌گرداند. ستون `progress_diff` به صورت عددی
    پردازش شده و مقادیر نامعتبر یا خالی با ۰ جایگزین می‌شوند.

    Args:
        username (str): نام کاربری که سوابق آن باید بارگذاری شود.

    Returns:
        pd.DataFrame: داده‌های کاربر شامل ستون‌های زیر:
            - username: نام کاربری
            - week_start: تاریخ شروع هفته
            - week_end: تاریخ پایان هفته
            - name: نام فعالیت
            - target: هدف فعالیت
            - done: میزان انجام شده
            - percent: درصد پیشرفت
            - note: یادداشت مرتبط با فعالیت
            - saved_at: تاریخ و زمان ذخیره فعالیت
            - week_feedback: بازخورد هفتگی
            - week_total_score: امتیاز کل هفته
            - progress_diff: تغییر پیشرفت نسبت به هفته قبل (عدد صحیح)

    Example:
        >>> df = load_user_history("ali")
        >>> df.head()
          username week_start week_end        name  target  done  percent note  ...

    Notes:
        - از ماژول  برای اتصال به پایگاه داده و `pandas.read_sql_query` برای بارگذاری داده‌ها استفاده می‌کند.
        - اگر ستون `progress_diff` مقادیر نامعتبر یا خالی داشته باشد، با ۰ جایگزین می‌شود.
        - داده‌ها بر اساس ستون `saved_at` به ترتیب صعودی مرتب می‌شوند.
    """


    res = supabase.table("user_activities").select("*").eq("username", username).order("saved_at",
                                                                                       asc=True).execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        df["progress_diff"] = pd.to_numeric(df["progress_diff"], errors='coerce').fillna(0).astype(int)
    return df


def get_progress_style(percent: int):
    """استایل progress bar براساس درصد """
    if percent >= 80:
        return "background: linear-gradient(90deg, #10b981, #059669);"
    elif percent >= 50:
        return "background: linear-gradient(90deg, #f59e0b, #d97706);"
    else:
        return "background: linear-gradient(90deg, #ef4444, #dc2626);"


def render_premium_week_section(
        group: pd.DataFrame,username:str, is_admin: bool = False
):
    """نمایش بخش هفتگی پریمیوم کاربران با طراحی تعاملی و واکنش‌گرا در Streamlit.

    این تابع یک بخش کامل از داشبورد هفتگی کاربر را رندر می‌کند که شامل:
    - نمایش هدر هفته با تاریخ شروع و پایان، امتیاز کل هفته، تغییر پیشرفت نسبت به هفته قبل و نام کاربر (در صورت ادمین بودن)
    - کارت‌های فعالیت‌ها با نمایش نام، درصد پیشرفت، وضعیت انجام، هدف و نوار پیشرفت گرافیکی
    - بازخورد کلی هفته با تحلیل ساده‌ی حس (مثبت، منفی، خنثی) و استایل‌های اختصاصی
    - استایل‌های CSS واکنش‌گرا برای دسکتاپ، موبایل و موبایل‌های خیلی کوچک

    Args:
        group (pd.DataFrame): داده‌های فعالیت‌های هفتگی کاربر. انتظار می‌رود شامل ستون‌های:
            - name: نام فعالیت
            - target: هدف فعالیت
            - done: میزان انجام شده
            - percent: درصد پیشرفت
            - note: یادداشت مرتبط با فعالیت
            - saved_at_dt: تاریخ ذخیره فعالیت به صورت datetime
            - week_start: تاریخ شروع هفته
            - week_end: تاریخ پایان هفته
            - week_total_score: امتیاز کل هفته
            - progress_diff: تغییر پیشرفت نسبت به هفته قبل
            - week_feedback: بازخورد کلی هفته
        username (str, اختیاری): نام کاربری برای نمایش در هدر (پیش‌فرض از st.session_state گرفته می‌شود).
        is_admin (bool, اختیاری): مشخص می‌کند که آیا کاربر ادمین است یا خیر. اگر True باشد، نام کاربر در هدر نمایش داده می‌شود.

    Returns:
        None: این تابع مستقیماً محتوای HTML و CSS را با استفاده از `st.markdown` در Streamlit رندر می‌کند و خروجی بازنمی‌گرداند.

    Features:
        - کارت‌های فعالیت با رنگ و آیکون متناسب با درصد پیشرفت
        - نوار پیشرفت پویا با گرادیان رنگ
        - تحلیل ساده حس بازخورد هفتگی (مثبت، منفی، خنثی) و نمایش با آیکون و رنگ مناسب
        - طراحی واکنش‌گرا برای نمایش در موبایل و دسکتاپ
        - قابلیت اضافه کردن استایل‌های اختصاصی برای admin و کاربر معمولی
        - جایگزین کردن placeholder اگر بازخورد هفته ثبت نشده باشد

    Example:
        >>> render_premium_week_section(group=df_user_week, username="ali", is_admin=True)

    Notes:
        - تابع از کتابخانه‌های `pandas`, `html` و `streamlit` استفاده می‌کند.
        - تمام CSSها به صورت inline و در ابتدای اجرای تابع inject می‌شوند.
        - این تابع برای استفاده در داشبورد Streamlit و نمایش بصری طراحی شده است و داده‌ها را مستقیماً از DataFrame ورودی می‌گیرد.
        - ستون‌های لازم در DataFrame باید با نام‌های مشخص شده موجود باشند تا کارت‌ها و هدر به درستی نمایش داده شوند.
    """

    activity_responsive_css = """
    <style>
    /* دسکتاپ: همون layout فعلی */
    .activity-card {
        background: rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 16px; margin: 12px 0;
        border: 1px solid rgba(148, 163, 184, 0.1); direction: rtl;
    }

    .activity-header {
        display: flex !important; justify-content: space-between; align-items: center; margin-bottom: 12px;
        flex-wrap: wrap; gap: 8px;
    }

    .activity-name {
        font-size: 16px; font-weight: 600; color: #f8fafc;
        display: flex; align-items: center; gap: 8px; flex: 1;
    }

    .activity-badge {
        display: flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 20px;
        font-weight: 600; font-size: 13px; border: 1px solid rgba(255, 255, 255, 0.1);
        white-space: nowrap; /* badge در یک خط بمونه */
    }

    .activity-stats {
        display: flex !important; flex-direction: row !important; flex-wrap: wrap; gap: 4px;
        margin-bottom: 12px; font-size: 13px; color: #cbd5e1; direction: rtl;
        justify-content: space-between; align-items: center; width: 100%;
    }

    .activity-stat-item {
        display: flex; align-items: center; gap: 4px; padding: 4px 6px;
        background: rgba(255, 255, 255, 0.05); border-radius: 6px;
        border: 1px solid rgba(148, 163, 184, 0.1); flex: 1; min-width: 90px;
        justify-content: center; /* center متن در هر item */
    }

    .activity-progress-container {
        background: rgba(255, 255, 255, 0.1); border-radius: 10px; padding: 2px;
        margin: 8px 0; height: 15px; position: relative; overflow: hidden; width: 100%;
    }

    .activity-progress-fill {
        height: 100%; border-radius: 8px; transition: width 1s ease;
        position: relative; /* width dynamic در HTML */
    }

    .activity-progress-text {
        position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
        font-size: 13px; font-weight: 600; color: white;
        text-shadow: 0 1px 2px rgba(0,0,0,0.5); white-space: nowrap;
    }

    /* موبایل: اجبار قوی‌تر به row، فشرده‌تر */
    @media (max-width: 768px) {
        .activity-card {
            padding: 8px !important; margin: 8px 0; border-radius: 10px;
        }

        .activity-header {
            gap: 4px !important; margin-bottom: 8px;
        }

        .activity-name {
            font-size: 14px; gap: 4px; flex: 2; /* نام بیشتر فضا بگیره */
        }

        .activity-badge {
            font-size: 12px; padding: 3px 6px !important; gap: 3px; flex: 1;
        }

        .activity-stats {
            flex-direction: row !important; gap: 2px !important; font-size: 12px;
            justify-content: space-around !important; /* پخش یکنواخت */
            margin-bottom: 6px;
        }

        .activity-stat-item {
            padding: 2px 4px !important; min-width: 60px !important; font-size: 10px;
            flex: none; /* اندازه ثابت، بدون کشش */
            gap: 2px;
        }

        .activity-progress-container {
            height: 12px !important; margin: 4px 0; padding: 1px;
        }

        .activity-progress-fill {
            border-radius: 6px;
        }

        .activity-progress-text {
            font-size: 10px; right: 4px;
        }
    }

    /* موبایل خیلی کوچک: wrap بهتر، اما row اولویت */
    @media (max-width: 480px) {
        .activity-header {
            flex-direction: row !important; /* همچنان row، اما اگر لازم wrap */
            align-items: flex-start; gap: 2px;
        }

        .activity-name {
            font-size: 13px; flex: 1.5;
        }

        .activity-badge {
            font-size: 11px; padding: 2px 4px; ustify-content: center;
        }

        .activity-stats {
            flex-wrap: wrap !important; gap: 3px; justify-content: space-between;
            /* دو تا در ردیف اول، یکی در دوم اگر جا نشد */
        }

        .activity-stat-item {
            min-width: 70px !important; flex: 1 1 45%; /* هر دو تا ۴۵% عرض */
            font-size: 10px; text-align: center; /* center برای زیبایی */
        }

        .activity-progress-container {
            height: 10px; /* حتی کوچکتر */
        }

        .activity-progress-text {
            font-size: 9px;
        }
    }
    </style>
    """
    st.markdown(activity_responsive_css, unsafe_allow_html=True)

    group = group.sort_values("saved_at_dt", ascending=True)
    first_row = group.iloc[0]
    week_start = first_row["week_start"]
    week_end = first_row["week_end"]
    week_total = int(first_row.get("week_total_score", 0))
    progress_diff = int(first_row.get("progress_diff", 0))
    feedback = str(first_row.get("week_feedback", "")).strip() or "—"

    # ✅ CSS سفارشی برای هدر - یک‌بار در ابتدای کد inject کن (merge با CSS قبلی)
    header_css = """
    <style>
    .header-container {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border-radius: 16px; padding: 24px; margin: 12px 0;
        border: 1px solid rgba(148, 163, 184, 0.2);
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        direction: rtl; text-align: right;
    }

    .header-top {
        display: flex; justify-content: space-between; align-items: center;
        flex-wrap: wrap; gap: 12px; margin-bottom: 20px; padding: 16px 0;
        border-bottom: 1px solid rgba(148, 163, 184, 0.1);
    }

    .header-date {
        font-size: 22px; font-weight: 700; color: #60a5fa;
        display: flex; align-items: center; gap: 8px;
    }

    .header-badges {
        display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
    }

    .header-badge {
        display: inline-flex; align-items: center; gap: 6px; 
        padding: 8px 16px; border-radius: 50px; font-size: 13px; font-weight: 600;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        cursor: pointer; /* برای hover */
    }

    .header-badge:hover {
        transform: scale(1.05); box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }

    /* موبایل: فشرده‌تر، row حفظ‌شده */
    @media (max-width: 768px) {
        .header-container {
            padding: 16px !important; margin: 8px 0; border-radius: 12px;
            box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.2); /* سبک‌تر */
        }

        .header-top {
            gap: 8px !important; padding: 12px 0; margin-bottom: 16px;
        }

        .header-date {
            font-size: 18px; gap: 6px; flex: 1; /* تاریخ فضا بگیره */
        }

        .header-badges {
            gap: 8px !important; justify-content: flex-end;
        }

        .header-badge {
            padding: 6px 12px !important; font-size: 12px; gap: 4px;
            border-radius: 25px; /* کمی کوچکتر */
        }
    }

    /* موبایل خیلی کوچک: column برای هدر، badgeها center */
    @media (max-width: 480px) {
        .header-top {
            flex-direction: column !important; align-items: center; text-align: center;
            gap: 10px !important; padding: 8px 0;
        }

        .header-date {
            font-size: 16px; justify-content: center;
        }

        .header-badges {
            gap: 6px !important; justify-content: center; width: 100%;
            flex-wrap: wrap; /* اگر ۳ تا باشه، wrap به دو ردیف */
        }

        .header-badge {
            padding: 5px 10px !important; font-size: 11px; gap: 3px;
            flex: 1 1 auto; min-width: 80px; justify-content: center;
        }
    }
    </style>
    """
    st.markdown(header_css, unsafe_allow_html=True)

    # Header با inline styles
    user_badge = ""
    if is_admin and username:
        user_badge = f"""
        <div class="header-badge" style="
            background: rgba(34, 197, 94, 0.2); color: #4ade80; 
            border: 1px solid rgba(34, 197, 94, 0.3);
        ">
            👤 {html.escape(username)}
        </div>
        """

    if progress_diff > 0:
        diff_badge_style = "background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4);"
        diff_emoji = "📈"
    elif progress_diff < 0:
        diff_badge_style = "background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3);"
        diff_emoji = "📉"
    else:
        diff_badge_style = "background: rgba(156, 163, 184, 0.2); color: #94a3b8; border: 1px solid rgba(156, 163, 184, 0.3);"
        diff_emoji = "🪨"

    score_badge = f"""
    <div class="header-badge" style="
        background: rgba(59, 130, 246, 0.2); color: #60a5fa; 
        border: 1px solid rgba(59, 130, 246, 0.3);
    ">
        ✨ {week_total}%
    </div>
    """

    diff_badge = f"""
    <div class="header-badge" style="
        {diff_badge_style}
    ">
        {diff_emoji} {progress_diff}%
    </div>
    """

    header_html = f"""
    <div class="header-container">
        <div class="header-top">
            <div class="header-date">
                🗓️ {week_start} تا {week_end}
            </div>
            <div class="header-badges">
                {user_badge}
                {score_badge}
                {diff_badge}
            </div>
        </div>
    </div>
    """

    st.markdown(header_html, unsafe_allow_html=True)

    # فعالیت‌ها
    total_activities = len(group)
    st.markdown(
        f"""
        <div style="margin-bottom: 16px;">
            <h4 style="color: #e2e8f0; margin: 0 0 16px 0; font-size: 18px; direction: rtl;">
                📋 فعالیت‌ها ({total_activities})
            </h4>
    """,
        unsafe_allow_html=True,
    )

    for idx, (_, row) in enumerate(group.iterrows(), 1):
        activity_name = html.escape(str(row.get("name", "")))
        target = int(row.get("target", 0))
        done = int(row.get("done", 0))
        percent = int(row.get("percent", 0))
        note = html.escape(str(row.get("note", "")))
        status = "✅" if done >= target else "🔄"
        status_text = "کامل" if done >= target else f"{done}/{target}"

        # Progress badge style
        if percent >= 80:
            progress_style = "background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3);"
            progress_emoji = "🧗‍♂️"
        elif percent >= 50:
            progress_style = "background: rgba(251, 191, 36, 0.2); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3);"
            progress_emoji = "🧭"
        else:
            progress_style = "background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3);"
            progress_emoji = "🪢"

        # Progress bar style
        if percent >= 80:
            bar_style = "background: linear-gradient(90deg, #10b981, #059669);"
        elif percent >= 50:
            bar_style = "background: linear-gradient(90deg, #f59e0b, #d97706);"
        else:
            bar_style = "background: linear-gradient(90deg, #ef4444, #dc2626);"

        activity_html = f"""
        <div class="activity-card">
            <div class="activity-header">
                <div class="activity-name">
                    {idx}. {activity_name}
                </div>
                <div class="activity-badge" style="{progress_style}">
                    {progress_emoji} {percent}%
                </div>
            </div>
            <div class="activity-stats">
                <div class="activity-stat-item">🧗 انجام: {done}</div>
                <div class="activity-stat-item">🎯 هدف: {target}</div>
                <div class="activity-stat-item">{status} وضعیت: {status_text}</div>
            </div>
            <div class="activity-progress-container">
                <div class="activity-progress-fill" style="width: {percent}%; {bar_style}">
                    <span class="activity-progress-text">{percent}%</span>
                </div>
            </div>
        </div>
        """

        st.markdown(activity_html, unsafe_allow_html=True)

        feedback_css = """
        <style>
        .feedback-card {
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.8), rgba(30, 41, 59, 0.6)); 
            border-radius: 12px; padding: 16px; margin: 16px 0; margin-top: 20px;
            border: 1px solid rgba(148, 163, 184, 0.2); direction: rtl; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            animation: fadeIn 0.5s ease-in;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .feedback-header {
            display: flex !important; align-items: center; gap: 8px; margin-bottom: 12px;
            color: #fbbf24; font-weight: 600; font-size: 15px; border-bottom: 1px solid rgba(251, 191, 36, 0.2);
            padding-bottom: 8px; flex-wrap: nowrap; /* جلوگیری از wrap ناخواسته */
            justify-content: flex-start; /* چپ‌چین برای rtl */
        }

        .feedback-content {
            color: #e2e8f0; line-height: 1.6; white-space: pre-wrap; font-size: 14px;
            word-break: break-word;
        }

        .feedback-placeholder {
            color: #94a3b8 !important; font-style: italic; cursor: pointer;
            border: 1px dashed rgba(148, 163, 184, 0.3); padding: 8px; border-radius: 6px;
            transition: background 0.2s ease; margin-top: 8px;
        }

        .feedback-placeholder:hover {
            background: rgba(148, 163, 184, 0.1);
        }

        .feedback-sentiment-badge {
            display: inline-flex !important; align-items: center; gap: 4px; padding: 4px 8px; border-radius: 8px;
            font-weight: 600; font-size: 12px; white-space: nowrap; /* badge در یک خط */
            transition: transform 0.2s ease; flex-shrink: 0; /* کوچک نشه */
        }

        .feedback-sentiment-badge:hover {
            transform: scale(1.05);
        }

        /* موبایل: row اجباری، فشرده‌تر */
        @media (max-width: 768px) {
            .feedback-card {
                padding: 12px !important; margin: 12px 0;
            }

            .feedback-header {
                font-size: 13px; gap: 6px !important; padding-bottom: 6px;
                flex-direction: row !important; /* اجبار row */
                justify-content: space-between; /* پخش: متن چپ، badge راست */
            }

            .feedback-content, .feedback-placeholder {
                font-size: 12px; line-height: 1.5;
            }

            .feedback-sentiment-badge {
                font-size: 10px; padding: 3px 6px !important; gap: 2px; border-radius: 6px;
            }

            .feedback-placeholder {
                font-size: 11px; padding: 6px;
            }
        }

        /* موبایل خیلی کوچک: همچنان row، اما فشرده حداکثری */
        @media (max-width: 480px) {
            .feedback-header {
                font-size: 12px !important; gap: 4px !important; padding-bottom: 4px;
                flex-direction: row !important; /* اجبار row - نه column */
                align-items: flex-start; flex-wrap: nowrap; /* بدون wrap */
                justify-content: flex-start; /* یا space-between اگر بخوای badge راست بره */
                margin-bottom: 8px;
            }

            .feedback-content {
                font-size: 11px;
            }

            .feedback-sentiment-badge {
                font-size: 9px !important; padding: 2px 4px !important; gap: 1px;
                min-width: auto; /* کوچک حداکثری */
            }

            .feedback-placeholder {
                font-size: 10px; padding: 4px;
            }
        }
        </style>
        """
        st.markdown(feedback_css, unsafe_allow_html=True)

        if note:
            st.markdown(
                f"""
            <div style="
                background: rgba(15, 23, 42, 0.6); border-radius: 8px; padding: 12px; margin-top: 8px;
                border: 1px solid rgba(148, 163, 184, 0.2); font-size: 13px; color: #e2e8f0;
                line-height: 1.6; direction: rtl;
            ">
                📝 {note}
            </div>
            """,
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

    sentiment = "neutral"
    sentiment_emoji = "🪢"
    sentiment_style = "background: rgba(156, 163, 175, 0.2); color: #9ca3af; border: 1px solid rgba(156, 163, 175, 0.3);"

    if feedback and feedback != "—" and feedback != "":
        positive_words = ["عالی", "خوب", "موفق", "لذت", "پیشرفت", "انرژی", "افتخار"]
        negative_words = ["سخت", "خسته", "فراموش", "مشکل", "افت"]
        if any(word in feedback.lower() for word in positive_words):
            sentiment = "positive"
            sentiment_emoji = "🧗‍♂️"
            sentiment_style = "background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3);"
        elif any(word in feedback.lower() for word in negative_words):
            sentiment = "negative"
            sentiment_emoji = "🧭"
            sentiment_style = "background: rgba(251, 191, 36, 0.2); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3);"

    if feedback and feedback != "—" and feedback != "":
        feedback_html = f"""
        <div class="feedback-card">
            <div class="feedback-header" style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    📝 بازخورد کلی هفته :
                </div>
                <span class="feedback-sentiment-badge" style="{sentiment_style}">
                    {sentiment_emoji} حس کلی: {sentiment.title()}
                </span>
            </div>
            <div class="feedback-content">
                {feedback}
            </div>
        </div>
        """
        st.markdown(feedback_html, unsafe_allow_html=True)
    else:
        # placeholder اگر خالی باشه
        st.markdown("""
        <div class="feedback-card">
            <div class="feedback-header">
                📝 بازخورد کلی هفته
            </div>
            <div class="feedback-placeholder" onclick="document.getElementById('feedback-textarea').scrollIntoView(); return false;">
                💭 بازخوردی ثبت نشده است. تجربیاتت رو بنویس تا مسیرت بهتر بشه! (مثل چالش‌ها یا موفقیت‌های این هفته)
            </div>
        </div>
        """, unsafe_allow_html=True)


def render_premium_history_ui(
        df: pd.DataFrame,
        *,
        key_prefix: str,
        empty_message: str,
        show_user_filter: bool = False,
):
    """رندر رابط کاربری Premium برای مشاهده تاریخچه فعالیت‌های کاربران در Streamlit.

    این تابع یک بخش کامل برای نمایش تاریخچه فعالیت‌های هفتگی کاربران را با طراحی Premium و
    inline CSS ارائه می‌دهد. قابلیت‌های اصلی شامل:
    - نمایش آمار کلی (تعداد فعالیت‌ها، هفته‌ها، میانگین و بهترین امتیاز)
    - فیلتر جستجو در نام فعالیت‌ها، یادداشت‌ها و بازخوردها
    - فیلتر بر اساس کاربر (در صورت فعال بودن show_user_filter)
    - گروه‌بندی فعالیت‌ها بر اساس هفته و کاربر
    - نمایش هر هفته با استفاده از تابع `render_premium_week_section`

    Args:
        df (pd.DataFrame): داده‌های فعالیت‌های کاربران شامل ستون‌هایی مانند:
            - username: نام کاربر
            - week_start: تاریخ شروع هفته
            - week_end: تاریخ پایان هفته
            - name: نام فعالیت
            - target: هدف فعالیت
            - done: میزان انجام شده
            - percent: درصد پیشرفت
            - note: یادداشت فعالیت
            - saved_at: زمان ذخیره فعالیت
            - week_total_score: امتیاز کل هفته
            - progress_diff: تغییر پیشرفت نسبت به هفته قبل
            - week_feedback: بازخورد کلی هفته
        key_prefix (str): پیشوند برای کلیدهای ویجت‌های Streamlit (مانند text_input و selectbox)
        empty_message (str): پیامی که در صورت خالی بودن DataFrame نمایش داده می‌شود
        show_user_filter (bool, اختیاری): اگر True باشد، امکان فیلتر بر اساس کاربر فعال می‌شود
    Returns:
        None: این تابع مستقیماً رابط کاربری را در Streamlit رندر می‌کند و خروجی بازنمی‌گرداند.

    Features:
        - فیلترهای جستجو و انتخاب کاربر برای مشاهده داده‌های خاص
        - مرتب‌سازی خودکار بر اساس تاریخ شروع هفته و زمان ذخیره
        - نمایش گروه‌بندی شده هفته‌ها با جزئیات هر فعالیت
        - استایل‌های واکنش‌گرا برای موبایل، تبلت و دسکتاپ
        - محاسبه و نمایش آمار کلی برای هر بخش و کل داده‌ها

    Example:
        >>> render_premium_history_ui(
                df=df_user_history,
                key_prefix="user_hist",
                empty_message="هیچ داده‌ای برای نمایش وجود ندارد.",
                show_user_filter=True,
            )

    Notes:
        - تابع از کتابخانه‌های `pandas` و `streamlit` استفاده می‌کند.
        - ستون‌های ضروری در DataFrame باید موجود باشند تا بخش‌ها و فیلترها به درستی کار کنند.
        - تابع برای استفاده در داشبورد Streamlit و نمایش داده‌های پریمیوم طراحی شده است.
        - داده‌ها بر اساس هفته و زمان ذخیره مرتب و گروه‌بندی می‌شوند.
    """

    if df.empty:
        st.info(empty_message)
        return

    # آماده‌سازی داده‌ها
    working_df = df.copy()
    working_df["progress_diff"] = pd.to_numeric(working_df["progress_diff"], errors='coerce').fillna(0).astype(int)

    # Section جستجو و فیلتر - طراحی
    col1, col2 = st.columns([3, 1])

    with col1:
        search_value = st.text_input(
            "🔍 جستجو در فعالیت‌ها، یادداشت‌ها یا بازخوردها",
            placeholder="ورزش، کتاب، مدیتیشن، پیشرفت...",
            key=f"{key_prefix}_search",
            help="هر کلمه‌ای که به یاد داری رو تایپ کن",
        )

    with col2:
        if show_user_filter:
            user_options = ["همه کاربران"] + sorted(
                working_df["username"].unique().tolist()
            )
            selected_user = st.selectbox(
                "👥 کاربر",
                options=user_options,
                index=0,
                key=f"{key_prefix}_user",
            )
        else:
            selected_user = None

    # اعمال فیلترها
    original_df = working_df.copy()
    if search_value:
        mask_name = working_df["name"].str.contains(
            search_value, case=False, na=False, regex=False
        )
        mask_note = working_df["note"].str.contains(
            search_value, case=False, na=False, regex=False
        )
        mask_feedback = working_df["week_feedback"].str.contains(
            search_value, case=False, na=False, regex=False
        )
        working_df = working_df[mask_name | mask_note | mask_feedback].copy()

    if show_user_filter and selected_user and selected_user != "همه کاربران":
        working_df = working_df[working_df["username"] == selected_user].copy()

    total_items_original = len(original_df)
    avg_score_original = (
        original_df["week_total_score"].mean() if not original_df.empty else 0
    )
    best_score_original = (
        original_df["week_total_score"].max() if not original_df.empty else 0
    )
    num_weeks_original = (
        len(original_df.groupby(["week_start", "week_end"]))
        if not original_df.empty
        else 0
    )
    stats_html = f"""<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-top: 20px; padding: 16px; background: rgba(255, 255, 255, 0.02); border-radius: 12px; border: 1px solid rgba(148, 163, 184, 0.1); direction: rtl; text-align: center;">
   <div style="padding: 12px; background: rgba(255, 99, 71, 0.1); border-radius: 8px; border: 1px solid rgba(255, 99, 71, 0.2); display: flex; flex-direction: column; justify-content: center; align-items: center;">
      <div style="font-size: 20px; font-weight: 700; color: #ff6347; margin-bottom: 4px;">{total_items_original}</div>
      <div style="font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px;">فعالیت کل</div>
   </div>
   <div style="padding: 12px; background: rgba(54, 162, 235, 0.1); border-radius: 8px; border: 1px solid rgba(54, 162, 235, 0.2); display: flex; flex-direction: column; justify-content: center; align-items: center;">
      <div style="font-size: 20px; font-weight: 700; color: #4682b4; margin-bottom: 4px;">{num_weeks_original}</div>
      <div style="font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px;">هفته‌ها</div>
   </div>
   <div style="padding: 12px; background: rgba(75, 192, 192, 0.1); border-radius: 8px; border: 1px solid rgba(75, 192, 192, 0.2); display: flex; flex-direction: column; justify-content: center; align-items: center;">
      <div style="font-size: 20px; font-weight: 700; color: #20b2aa; margin-bottom: 4px;">{avg_score_original:.1f}%</div>
      <div style="font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px;">میانگین</div>
   </div>
   <div style="padding: 12px; background: rgba(255, 206, 86, 0.1); border-radius: 8px; border: 1px solid rgba(255, 206, 86, 0.2); display: flex; flex-direction: column; justify-content: center; align-items: center;">
      <div style="font-size: 20px; font-weight: 700; color: #d4a017; margin-bottom: 4px;">{best_score_original}%</div>
      <div style="font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px;">بهترین</div>
   </div>
</div>"""
    st.markdown(stats_html, unsafe_allow_html=True)
    if working_df.empty:
        st.warning("❌ هیچ گزارشی با این فیلترها پیدا نشد.")

    # مرتب‌سازی
    try:
        working_df["week_start_dt"] = working_df["week_start"].apply(
            jalali_to_gregorian
        )
        working_df["saved_at_dt"] = pd.to_datetime(
            working_df["saved_at"], errors="coerce"
        )
        working_df = working_df.sort_values(
            ["week_start_dt", "saved_at_dt"], ascending=[False, False]
        )
    except Exception:
        working_df["saved_at_dt"] = pd.to_datetime(
            working_df["saved_at"], errors="coerce"
        )
        working_df = working_df.sort_values("saved_at_dt", ascending=False)

    # نمایش هفته‌ها
    if show_user_filter and selected_user == "همه کاربران":
        grouped = working_df.groupby(["username", "week_start", "week_end"], sort=False)
        for (username_val, w_start, w_end), group in grouped:
            week_total = int(group.iloc[0]["week_total_score"])
            progress_diff = int(group.iloc[0]["progress_diff"])

            title = f"👤 {username_val} | 🗓️ {w_start} تا {w_end} | ✨ {week_total}%"
            if progress_diff != 0:
                title += f" | {'📈' if progress_diff > 0 else '📉'} {progress_diff}%"

            with st.expander(title, expanded=False):
                render_premium_week_section(group, username_val, is_admin=True)
    else:
        grouped = working_df.groupby(["week_start", "week_end"], sort=False)
        for (w_start, w_end), group in grouped:
            week_total = int(group.iloc[0]["week_total_score"])
            progress_diff = int(group.iloc[0]["progress_diff"])

            title = f"🗓️ {w_start} تا {w_end} | ✨ {week_total}%"
            if progress_diff != 0:
                title += f" | {'📈' if progress_diff > 0 else '📉'} {progress_diff}%"

            with st.expander(title, expanded=False):
                render_premium_week_section(group)


# --------------------------
# هدر و لوگو گروه
# --------------------------
def show_home_header():
    st.markdown(
        """
        <div class="k2-glass-card" style="display:flex; align-items:center; gap:20px; margin-bottom:26px;">
            <div style="
                width:72px; height:72px; border-radius:24px;
                background: linear-gradient(135deg, rgba(59,130,246,0.9), rgba(236,72,153,0.85));
                box-shadow: 0 18px 35px rgba(59,130,246,0.45);
                display:flex; align-items:center; justify-content:center;
                font-size:30px; font-weight:800; color:white;
            ">
                K2
            </div>
            <div style="display:flex; flex-direction:column; gap:6px;">
                <span style="font-size:22px; font-weight:700; color:#f8fafc; display:flex; align-items:center; gap:8px;">
                    🏔️ K2 — مسیر رشد فردی
                </span>
                <span style="font-size:14px; color:rgba(226, 232, 240, 0.75);">
                    قله‌ها برای کسانی‌اند که ایستادن را انتخاب نمی‌کنند ...
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------
# فونت فارسی
# --------------------------
font_path = FONTS_DIR / "vazir/Vazir-Medium.ttf"
font_b64 = None
if font_path.exists():
    with open(font_path, "rb") as f:
        font_data = f.read()
        font_b64 = base64.b64encode(font_data).decode()
    st.markdown(
        f"""
        <style>
        @font-face {{
              font-family: 'Vazir-Medium';
              src: url(data:font/ttf;base64,{font_b64}) format('truetype');
              font-weight: normal;
              font-style: normal;
        }}
        html, body, [class*="css"], div, span, p, h1, h2, h3, h4, h5, h6,
        input, textarea, button, label, li, th, td , span {{
            font-family: 'Vazir-Medium', sans-serif !important;
            letter-spacing: 0 !important;
            direction: rtl;
            text-align: right;
       }} 
        </style>
    """,
        unsafe_allow_html=True,
    )

# --------------------------
# URL تصویر K2 (از Imgur)
# --------------------------
background_url = "https://i.imgur.com/0jQN9Hj.png"  # URL مستقیم به تصویر

# --------------------------
# فزودن CSS سراسری تم شیشه‌ای
# --------------------------
GLASS_THEME_CSS = f"""
<style>
:root {{
    --glass-bg: rgba(15, 23, 42, 0.55);
    --glass-border: rgba(148, 163, 184, 0.35);
    --glass-highlight: rgba(59, 130, 246, 0.35);
    --glass-text: #e2e8f0;
    --glass-subtle: rgba(148, 163, 184, 0.4);
}}


[data-testid="stAppViewContainer"] {{
    background-image:
        linear-gradient(145deg, rgba(15, 23, 42, 0.65), rgba(30, 41, 59, 0.55)),
        radial-gradient(circle at 20% 20%, rgba(59,130,246,0.18), transparent 45%),
        radial-gradient(circle at 80% 10%, rgba(236,72,153,0.15), transparent 50%),
        url('{background_url}');
    background-size: cover, 100% 100%, 100% 100%, cover;
    background-repeat: no-repeat;
    background-position: center center;
    background-attachment: fixed;
    color: var(--glass-text);
}}

.k2-glass-card {{
    background: var(--glass-bg);
    border: 1px solid var(--glass-border);
    border-radius: 24px;
    padding: 28px 32px;
    box-shadow: 0 25px 45px rgba(15, 23, 42, 0.35);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    position: relative;
    overflow: hidden;
}}

.k2-glass-card::before {{
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(59,130,246,0.12), rgba(59,130,246,0));
    opacity: 0.8;
}}

.k2-glass-card::after {{
    content: "";
    position: absolute;
    inset: 0;
    border-radius: inherit;
    border: 1px solid rgba(255,255,255,0.04);
}}

.k2-glass-card > * {{
    position: relative;
    z-index: 2;
}}

.k2-login-wrapper {{
    max-width: 520px;
    margin: 60px auto 40px;
    padding: 0 16px;
}}

.k2-login-title {{
    font-size: 28px;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 10px;
    color: #f8fafc;
    margin-bottom: 12px;
}}

.k2-login-subtitle {{
    color: rgba(226, 232, 240, 0.8);
    font-size: 14px;
    line-height: 1.6;
    margin-bottom: 28px;
}}

div[data-testid="stTextInput"] input,
div[data-testid="stPasswordInput"] input {{
    background: rgba(15, 23, 42, 0.45);
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 16px;
    color: #f8fafc;
    padding: 12px 16px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.05);
}}

div[data-testid="stTextInput"] label,
div[data-testid="stPasswordInput"] label {{
    color: rgba(226, 232, 240, 0.85);
    font-weight: 600;
}}

.stButton > button {{
    background: linear-gradient(135deg, rgba(96, 165, 250, 0.9), rgba(59, 130, 246, 0.9));
    color: white;
    font-weight: 600;
    border-radius: 999px;
    border: none;
    padding: 10px 28px;
    box-shadow: 0 12px 25px rgba(59, 130, 246, 0.35);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}}

.stButton > button:hover {{
    transform: translateY(-2px);
    box-shadow: 0 18px 30px rgba(59, 130, 246, 0.45);
}}

@media (max-width: 640px) {{
    .k2-login-wrapper {{
        margin: 30px auto 20px;
    }}
    .k2-login-title {{
        font-size: 22px;
    }}
    .k2-glass-card {{
        padding: 22px 20px;
        border-radius: 20px;
    }}

    .k2-login-hero {{
    display: flex;
    flex-direction: column;
    gap: 16px;
}}

.k2-login-badge {{
    align-self: flex-start;
    padding: 6px 14px;
    border-radius: 999px;
    background: linear-gradient(135deg, rgba(96,165,250,0.25), rgba(59,130,246,0.15));
    border: 1px solid rgba(59,130,246,0.35);
    color: rgba(226,232,240,0.85);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.8px;
}}

.k2-login-title {{
    font-size: 32px;
    font-weight: 800;
    color: #f9fafb;
    margin: 0;
    line-height: 1.2;
    text-shadow: 0 8px 24px rgba(15,23,42,0.45);
}}

.k2-login-subtitle {{
    color: rgba(226,232,240,0.78);
    font-size: 15px;
    line-height: 1.9;
    max-width: 420px;
}}

.k2-login-motto {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    border-radius: 18px;
    background: rgba(15,23,42,0.4);
    border: 1px solid rgba(148,163,184,0.25);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    color: rgba(226,232,240,0.9);
    font-size: 13px;
}}

.k2-login-motto strong {{
    display: block;
    color: #93c5fd;
    margin-bottom: 2px;
    font-size: 13px;
}}

@media (max-width: 640px) {{
    .k2-login-title {{
        font-size: 26px;
    }}
    .k2-login-subtitle {{
        font-size: 13px;
        max-width: none;
    }}
    .k2-login-motto {{
        font-size: 12px;
        padding: 12px;
        border-radius: 14px;
    }}
}}
</style>
"""
st.markdown(GLASS_THEME_CSS, unsafe_allow_html=True)

st.set_page_config(page_title="K2 - مسیر رشد فردی", page_icon="⛰️", layout="centered")
# --------------------------
# مقداردهی اولیه session_state
# --------------------------
for key, default in [
    ("users", {}),
    ("logged_in", False),
    ("username", None),
    ("role", "user"),
    ("week_set", False),
    ("activities", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---- منطق نمایش پایدار بین rerun‌ها ----
if "banner" in st.session_state:
    banner_data = st.session_state.pop("banner")
    if banner_data.get("position") == "top":
        timed_message(**banner_data)

show_home_header()
st.markdown("---")

# --------------------------
# ورود / ثبت‌نام با ادمین
# --------------------------
if not st.session_state.logged_in:
    with st.container():
        st.markdown("""
        <style>
        .k2-login-card {
          background: rgba(15, 23, 42, 0.6);
          backdrop-filter: blur(20px);
          border-radius: 24px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          padding: 32px 28px;
          margin: 40px auto;
          box-shadow: 0 10px 40px rgba(0,0,0,0.35);
          color: #f1f5f9;
          max-width: 520px;
          direction: rtl;
        }

        .k2-login-card h1 {
          font-size: 32px;
          font-weight: 800;
          color: #f9fafb;
          text-align: center;
          margin-bottom: 10px;
          text-shadow: 0 6px 18px rgba(59,130,246,0.3);
        }

        .k2-login-badge {
          display: inline-block;
          padding: 8px 18px;
          border-radius: 999px;
          background: linear-gradient(135deg, rgba(96,165,250,0.3), rgba(59,130,246,0.2));
          border: 1px solid rgba(59,130,246,0.4);
          color: rgba(226,232,240,0.9);
          font-size: 13px;
          font-weight: 700;
          margin-bottom: 16px;
        }

        .k2-login-subtitle {
          color: rgba(226,232,240,0.85);
          font-size: 15px;
          line-height: 1.9;
          text-align: justify;
          margin-bottom: 20px;
        }

        .k2-login-subtitle b {
          color: #93c5fd;
        }

        .k2-login-motto {
          margin-top: 24px;
          padding: 14px 16px;
          border-radius: 16px;
          background: rgba(30, 41, 59, 0.6);
          border: 1px solid rgba(148,163,184,0.25);
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 13px;
          color: rgba(226,232,240,0.9);
          justify-content: center;
        }

        .k2-login-motto strong {
          color: #60a5fa;
          font-weight: 700;
        }

        @media (max-width: 640px) {
          .k2-login-card {
            padding: 22px 18px;
            border-radius: 18px;
            margin: 20px auto;
          }
          .k2-login-card h1 {
            font-size: 26px;
          }
          .k2-login-subtitle {
            font-size: 13px;
            line-height: 1.7;
          }
          .k2-login-motto {
            font-size: 12px;
            flex-direction: column;
            text-align: center;
          }
        }
        </style>

        <div class="k2-login-card">
          <div class="k2-login-badge">🔭 چشم‌انداز صعود</div>
          <h1>K2 Base Camp 🧗</h1>
          <div class="k2-login-subtitle">
            <b>هر صعود از جرأتِ اولین گام آغاز می‌شود. 🚶‍♂️</b><br>
            صعود فقط بالا رفتن نیست؛ سفری‌ست به درون، بازگشتی به خویشتن. 🌿<br>
            هر قله‌ای داستانی دارد و داستان تو از همین لحظه آغاز می‌شود. ✨<br>
            هر قله‌ای را که فتح می‌کنی، خودت را دوباره معنا می‌کنی؛ زیرا بلندی، پاداشِ پایداری‌ست. 🏔️<br>
            امروز آغاز کن، که فردا از قله‌ها سخن بگویی — از قله‌هایی که درونت ساخته‌ای. 🌅
          </div>
          <div class="k2-login-motto">
            🎒 <strong>سه‌گانهٔ صعود:</strong> امیدواری، دیسیپلین، هم‌نوردی.
          </div>
        </div>
        """, unsafe_allow_html=True)

        raw_username = st.text_input("نام هم‌نورد", placeholder="مثال: اززو قره")
        password = st.text_input("رمز عبور", type="password", placeholder="رمز عبورت رو اینجا بنویس")
        st.markdown(f'<div>', unsafe_allow_html=True)
        login_btn = st.button("🚀 ورود / ثبت‌نام")
        st.markdown("</div></div></div>", unsafe_allow_html=True)

        if login_btn:
            if not raw_username or not password:
                timed_message("error", "نام کاربری و رمز را وارد کنید.")
            else:
                username = sanitize_username(raw_username)
                user = get_user(username)
                admin_user, admin_pw = get_admin_cred()
                if username == admin_user and password == admin_pw:
                    if not user:
                        create_user(admin_user, admin_pw, "admin")
                        user = get_user(admin_user)
                    if user and verify_password(admin_pw, user["password_hash"]):
                        st.session_state.update(
                            logged_in=True, username=admin_user, role="admin"
                        )
                        st.session_state["banner"] = {
                            "message": "خوش‌آمدی BashiYeka 🌄",
                            "msg_type": "success",
                            "position": "top",
                        }
                    else:
                        timed_message("error", "خطا در ایجاد حساب BashiYeka.")
                else:
                    if user:
                        if verify_password(password, user["password_hash"]):
                            st.session_state.update(
                                logged_in=True, username=username, role=user["role"]
                            )
                            st.session_state["banner"] = {
                                "message": f"خوش‌آمدی {username} 🌄",
                                "msg_type": "success",
                                "position": "top",
                            }
                            st.rerun()
                        else:
                            timed_message("error", "رمز اشتباه است.")
                    else:
                        if create_user(username, password):
                            st.session_state.update(
                                logged_in=True, username=username, role="user"
                            )
                            st.session_state["banner"] = {
                                "message": f"حساب ساخته شد و وارد شدی — خوش‌آمدی {username} 🌄",
                                "msg_type": "success",
                                "position": "top",
                            }
                        else:
                            timed_message("error", "نام کاربری تکراری است.")
    st.stop()

# --- کارت خوش‌آمدگویی با تنظیمات بازشونده ---

username = st.session_state.username
safe_username = sanitize_username(username)
user_img_path = IMAGES_DIR / f"{safe_username}.png"

# بررسی تصویر پروفایل
user_img_url = None
if user_img_path.exists():
    user_img_url = f"data:image/png;base64,{base64.b64encode(open(user_img_path, 'rb').read()).decode()}"

# مقدار پیش‌فرض نمایش تنظیمات
if "show_settings" not in st.session_state:
    st.session_state.show_settings = False

# --- CSS ---
WELCOME_CSS = """
<style>
.user-card {
    position: relative;
    background: linear-gradient(135deg, rgba(15,23,42,0.8), rgba(30,41,59,0.75));
    border: 1px solid rgba(148,163,184,0.2);
    border-radius: 24px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    padding: 40px 30px 25px;
    margin: 25px 0;
    text-align: center;
    direction: rtl;
    color: #e2e8f0;
    backdrop-filter: blur(18px);
    overflow: hidden;
}
.user-avatar {
    width: 120px;
    height: 120px;
    border-radius: 50%;
    border: 3px solid rgba(59,130,246,0.6);
    box-shadow: 0 0 25px rgba(59,130,246,0.3);
    object-fit: cover;
    margin: 0 auto 18px;
    display: block;
}
.user-name {
    font-size: 26px;
    font-weight: 800;
    background: linear-gradient(135deg, #60a5fa, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 4px;
    text-align: center;
}
.user-sub {
    color: #cbd5e1;
    font-size: 18px;
    margin-bottom: 20px;
    text-align: center;
}
.logout-btn {
    background: linear-gradient(135deg, #ef4444, #dc2626);
    color: white;
    border: none;
    border-radius: 25px;
    padding: 10px 24px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
}
.logout-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 18px rgba(239,68,68,0.3);
}
.settings-btn {
    position: absolute;
    top: 15px;
    left: 15px;
    background: rgba(59,130,246,0.15);
    border: 1px solid rgba(59,130,246,0.3);
    color: #93c5fd;
    border-radius: 50%;
    width: 42px;
    height: 42px;
    font-size: 20px;
    cursor: pointer;
    transition: all 0.3s ease;
}
.settings-btn:hover {
    background: rgba(59,130,246,0.25);
    transform: scale(1.1);
}

/* بخش تنظیمات */
.settings-panel {
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.4s ease-in-out, opacity 0.4s ease-in-out;
    opacity: 0;
}
.settings-panel.open {
    max-height: 600px;
    opacity: 1;
    margin-top: 15px;
    padding-top: 20px;
    border-top: 1px solid rgba(148,163,184,0.2);
}
.settings-panel h4 {
    color: #93c5fd;
    margin-bottom: 12px;
}
@media (max-width: 640px) {
    .user-avatar { width: 95px; height: 95px; }
    .user-name { font-size: 22px; }
    .user-sub { font-size: 13px; }
    .logout-btn { padding: 8px 20px; font-size: 13px; }
    .settings-btn { width: 36px; height: 36px; font-size: 18px; }
}
</style>
"""
st.markdown(WELCOME_CSS, unsafe_allow_html=True)

# --- HTML کارت ---
html_avatar = (
    f'<img src="{user_img_url}" class="user-avatar"/>'
    if user_img_url
    else '<div class="user-avatar" style="background:#1e293b;display:flex;align-items:center;justify-content:center;color:#64748b;font-size:40px;">👤</div>'
)

st.markdown(f"""
<div class="user-card">
    {html_avatar}
    <div class="user-name"><span>👋</span>
    خوش اومدی
{html.escape(username)}
دادا
</div>
    <div class="user-sub">از همین‌جا به قله بعدی صعود کن 🏔️</div>
    <form action="#" method="post">
        <button class="logout-btn" onclick="window.location.reload()">🚪 خروج</button>
    </form>
</div>
""", unsafe_allow_html=True)

# --- کنترل باز/بسته تنظیمات ---
st.markdown("""
<script>
window.addEventListener('message', (event) => {
    if (event.data?.type === 'toggle-settings') {
        const frame = parent.document.querySelector('iframe');
        if (frame) {
            frame.contentWindow.postMessage({type:'streamlit:setComponentValue', key:'toggleSettings', value:true}, '*');
        }
    }
});
</script>
""", unsafe_allow_html=True)

# دکمه تنظیمات (تغییر حالت)
if "toggleSettings" not in st.session_state:
    st.session_state.toggleSettings = False

if st.session_state.show_settings:
    panel_class = "settings-panel open"
else:
    panel_class = "settings-panel"

# دکمه باز/بسته تنظیمات
if st.button("⚙️ تنظیمات کاربر", use_container_width=True):
    st.session_state.show_settings = not st.session_state.show_settings
    st.rerun()

# --- محتوای تنظیمات ---
with st.container():
    st.markdown(f'<div class="{panel_class}">', unsafe_allow_html=True)
    if st.session_state.show_settings:
        st.markdown("### ⚙️ تنظیمات کاربر")

        uploaded_file = st.file_uploader("🖼️ تغییر عکس پروفایل", type=["png", "jpg"])
        if uploaded_file is not None:
            with open(user_img_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            timed_message("success", "📸 عکس پروفایل با موفقیت آپلود شد.")
            st.rerun()

        new_password = st.text_input("🔒 تغییر رمز عبور", type="password")
        if st.button("💾 ثبت رمز جدید"):
            if new_password.strip():
                change_password(username, new_password)
                timed_message("success", "✅ رمز عبور با موفقیت تغییر کرد!")
    st.markdown("</div>", unsafe_allow_html=True)

# --------------------------
# بازه هفته
# --------------------------
if not st.session_state.week_set:
    st.markdown("### اطلاعات هفته")
    week_start = st.text_input(
        "تاریخ شروع (شمسی - YYYY/MM/DD)", placeholder="۱۴۰۴/۰۷/۰۱"
    )
    week_end = st.text_input(
        "تاریخ پایان (شمسی - YYYY/MM/DD)", placeholder="۱۴۰۴/۰۷/۰۷"
    )
    timed_message(
        "info",
        "📅 برای افزودن فعالیت ها لطفاً ابتدا بازه هفته را تعیین کنید.",
    )
    if st.button("▶️ تایید بازه هفته"):
        if not (validate_jalali_date(week_start) and validate_jalali_date(week_end)):
            timed_message("error", "فرمت تاریخ اشتباه است یا تاریخ نامعتبر است.")
        else:
            hist = load_user_history(username)
            duplicate = (
                    not hist.empty
                    and (
                            (hist["week_start"] == week_start) & (hist["week_end"] == week_end)
                    ).any()
            )

            if duplicate:
                timed_message(
                    "warning",
                    "این بازه هفته قبلاً ثبت شده است — لطفاً بازه دیگری انتخاب کنید.",
                )
            else:
                st.session_state.week_start = week_start
                st.session_state.week_end = week_end
                st.session_state.week_set = True
                st.session_state.activities = []
                timed_message("success", "بازه هفته ثبت شد.")
                st.rerun()
else:
    week_start = st.session_state.week_start
    week_end = st.session_state.week_end
    st.markdown(f"#### 📅 برنامهٔ هفتگی {username} — {week_start} تا {week_end}")

# --------------------------
# افزودن فعالیت‌ها
# --------------------------
if st.session_state.week_set:
    st.markdown("---")
    st.subheader("افزودن فعالیت جدید")

    with st.form("add_activity_form", clear_on_submit=True):
        name = st.text_input(
            "نام فعالیت", placeholder=f"فعالیت {len(st.session_state.activities) + 1}"
        )
        target = st.number_input("تعداد هدف", min_value=0, value=0)
        done = st.number_input("تعداد انجام‌شده", min_value=0, value=0)
        note = st.text_area("یادداشت کوتاه", height=60)
        submitted = st.form_submit_button("➕ افزودن فعالیت")

        if submitted:
            percent = min(round(done / target * 100), 100)
            activity = {
                "name": name.strip() or f"فعالیت {len(st.session_state.activities) + 1}",
                "target": target,
                "done": done,
                "percent": percent,
                "note": note.strip(),
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            st.session_state.activities.append(activity)
            timed_message(
                "success", f"آیتم {activity['name']} با {percent}% اضافه شد."
            )
            time.sleep(3)
            st.rerun()

    # --------------------------
    # نمایش پیشرفت هفته
    # --------------------------
    total_score = None
    if st.session_state.activities:
        st.markdown("---")
        st.subheader("📊 پیشرفت هفته")
        total_list = []
        activities = st.session_state.activities
        for i, act in enumerate(reversed(activities), start=1):
            index = len(activities) - i + 1
            st.markdown(
                f"""
            <div style='
                padding:12px 16px;
                border-radius:12px;
                background: linear-gradient(145deg, #1f2937, #111827);
                color:#f9fafb;
                font-weight:600;
                margin-bottom:12px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.4);
                border: 1px solid rgba(255,255,255,0.1);
                transition: transform 0.2s, box-shadow 0.2s;
            '>
                {index}. {act['name']} - {act["percent"]}%
            </div>
            """,
                unsafe_allow_html=True,
            )
            st.progress(act["percent"] / 100.0)
            st.markdown(
                f"<i>{motivational_message(act['percent'])}</i>", unsafe_allow_html=True
            )
            total_list.append(act["percent"])
        total_score = round(sum(total_list) / len(total_list))
        st.markdown(f"### 🔹 میانگین کل هفته: {total_score}%")
        st.progress(total_score / 100.0)

    # --------------------------
    # ذخیره گزارش نهایی
    # --------------------------
    st.markdown("---")
    st.subheader("🔖 بازخورد کلی هفته")
    week_feedback = st.text_area("✍️ بازخورد کلی هفته", max_chars=500, height=120)

    if "save_message" in st.session_state and st.session_state.save_message:
        st.markdown(st.session_state.save_message, unsafe_allow_html=True)
        if st.button("ادامه"):
            st.session_state.save_message = None
            st.session_state.activities = []
            st.session_state.week_set = False
            st.rerun()
    else:
        if st.button("📥 ذخیره گزارش نهایی"):
            if not st.session_state.activities:
                timed_message("error", "ابتدا حداقل یک آیتم اضافه کن.")
            else:
                # محاسبه درصد کل
                total_list = [act["percent"] for act in st.session_state.activities]
                total_score = (
                    round(sum(total_list) / len(total_list)) if total_list else 0
                )
                # --- محاسبه progress_diff ---
                hist = load_user_history(username)
                if not hist.empty:
                    prev_weeks = hist[hist["week_start"] < week_start]
                    if not prev_weeks.empty:
                        # آخرین هفته قبلی
                        last_week_score = int(prev_weeks["week_total_score"].iloc[0] or 0)
                        diff = total_score - last_week_score
                    else:
                        diff = 0  # اولین هفته
                else:
                    diff = 0

                diff = int(diff or 0)
                # حالا diff را به همه فعالیت‌ها اضافه می‌کنیم
                for act in st.session_state.activities:
                    act["progress_diff"] = (
                        diff  # همه فعالیت‌های یک هفته یک مقدار diff دارند
                    )

                # ذخیره در SQLite
                append_user_history(
                    username,
                    st.session_state.activities,
                    week_start,
                    week_end,
                    week_feedback,
                    total_score,
                )

                # بارگذاری تاریخچه برای مقایسه
                hist = load_user_history(username)
                if hist.empty:
                    timed_message(
                        "info", "📊 این اولین هفتهٔ ثبت ‌شدهٔ توئه — شروع خوبی داری 💫"
                    )
                else:
                    # گروه‌بندی بر اساس هفته برای پیدا کردن هفته‌های کامل
                    hist["week_key"] = hist["week_start"] + "|" + hist["week_end"]
                    week_groups = hist.groupby("week_key").first().reset_index()
                    week_groups = week_groups.sort_values("week_start", ascending=False)

                    # پیدا کردن هفته فعلی و قبلی
                    current_week_key = f"{week_start}|{week_end}"
                    current_in_history = week_groups[
                        week_groups["week_key"] == current_week_key
                        ]

                    if len(week_groups) > 1:
                        # جدیدترین هفته قبل از هفته فعلی
                        prev_week_row = (
                            week_groups[week_groups["week_start"] < week_start].iloc[0]
                            if not week_groups[
                                week_groups["week_start"] < week_start
                                ].empty
                            else None
                        )
                        if prev_week_row is not None:
                            last_week_score = int(prev_week_row["week_total_score"])
                            diff = total_score - last_week_score
                            if diff > 0:
                                timed_message(
                                    "success",
                                    f"🔼 عالی! نسبت به هفته قبل {diff}% پیشرفت داشتی 👏",
                                )
                            elif diff < 0:
                                timed_message(
                                    "warning",
                                    f"🔽 این هفته {abs(diff)}٪ افت کردی، ولی ادامه بده 💪",
                                )
                            else:
                                timed_message(
                                    "info",
                                    "⚖️ عملکردت مشابه هفته قبل بوده — ثبات عالیه ✨",
                                )
                        else:
                            timed_message(
                                "info",
                                "📊 این اولین هفتهٔ ثبت ‌شدهٔ توئه — شروع خوبی داری 💫",
                            )
                    else:
                        timed_message(
                            "info", "📊 این اولین هفتهٔ ثبت ‌شدهٔ توئه — شروع خوبی داری 💫"
                        )

                timed_message("success", "گزارش این هفته ذخیره شد.")
                st.session_state.activities = []
                st.session_state.week_set = False
                st.rerun()

# --------------------------
# مشاهده تاریخچه
# --------------------------
st.markdown("---")
st.subheader("🏔️ مسیرهای پیموده‌شده")

# CSS مدرن و زیبا
PREMIUM_CSS = """
<style>
.premium-history {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    border-radius: 16px;
    padding: 24px;
    margin: 12px 0;
    border: 1px solid rgba(148, 163, 184, 0.2);
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.1);
}
.premium-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
    padding: 16px 0;
    border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}
.premium-title {
    font-size: 22px;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    display: flex;
    align-items: center;
    gap: 8px;
}
.premium-meta {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
}
.premium-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border-radius: 50px;
    font-size: 13px;
    font-weight: 600;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    transition: all 0.3s ease;
}
.premium-badge:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}
.badge-score {
    background: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
    border-color: rgba(59, 130, 246, 0.3);
}
.badge-user {
    background: rgba(34, 197, 94, 0.15);
    color: #4ade80;
    border-color: rgba(34, 197, 94, 0.3);
}
.badge-diff-up {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
    border-color: rgba(34, 197, 94, 0.4);
    animation: pulse-green 2s infinite;
}
.badge-diff-down {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border-color: rgba(239, 68, 68, 0.3);
}
.badge-diff-flat {
    background: rgba(156, 163, 184, 0.15);
    color: #94a3b8;
    border-color: rgba(156, 163, 184, 0.3);
}
@keyframes pulse-green {
    0%, 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.4); }
    50% { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }
}

.activity-card {
    background: rgba(255, 255, 255, 0.03);
    border-radius: 12px;
    padding: 16px;
    margin: 12px 0;
    border: 1px solid rgba(148, 163, 184, 0.1);
    backdrop-filter: blur(10px);
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}
.activity-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899);
    transform: scaleX(0);
    transition: transform 0.3s ease;
}
.activity-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
    border-color: rgba(59, 130, 246, 0.3);
}
.activity-card:hover::before {
    transform: scaleX(1);
}
.activity-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    flex-wrap: wrap;
    gap: 8px;
}
.activity-title {
    font-size: 16px;
    font-weight: 600;
    color: #f8fafc;
    display: flex;
    align-items: center;
    gap: 8px;
}
.activity-progress-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 20px;
    font-weight: 600;
    font-size: 13px;
    border: 1px solid rgba(255, 255, 255, 0.1);
}
.progress-high { 
    background: rgba(34, 197, 94, 0.2); 
    color: #4ade80; 
    border-color: rgba(34, 197, 94, 0.3);
    box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.1);
}
.progress-medium { 
    background: rgba(251, 191, 36, 0.2); 
    color: #fbbf24; 
    border-color: rgba(251, 191, 36, 0.3);
    box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.1);
}
.progress-low { 
    background: rgba(239, 68, 68, 0.2); 
    color: #f87171; 
    border-color: rgba(239, 68, 68, 0.3);
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
}
.activity-details {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 8px;
    margin-bottom: 12px;
    font-size: 13px;
    color: #cbd5e1;
}
.detail-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 6px;
    border: 1px solid rgba(148, 163, 184, 0.1);
}
.activity-note {
    background: rgba(15, 23, 42, 0.6);
    border-radius: 8px;
    padding: 12px;
    margin-top: 8px;
    border: 1px solid rgba(148, 163, 184, 0.2);
    font-size: 13px;
    color: #e2e8f0;
    line-height: 1.6;
}
.activity-progress-bar {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    padding: 2px;
    margin: 8px 0;
    height: 8px;
    position: relative;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    border-radius: 8px;
    transition: width 1s ease;
    position: relative;
}
.progress-fill::after {
    content: attr(data-percent);
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 11px;
    font-weight: 600;
    color: white;
    text-shadow: 0 1px 2px rgba(0,0,0,0.5);
}

.feedback-section {
    margin-top: 20px;
    padding: 16px;
    background: linear-gradient(135deg, rgba(15, 23, 42, 0.8), rgba(30, 41, 59, 0.8));
    border-radius: 12px;
    border: 1px solid rgba(148, 163, 184, 0.2);
    backdrop-filter: blur(10px);
}
.feedback-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
    color: #fbbf24;
    font-weight: 600;
    font-size: 15px;
}
.feedback-content {
    color: #e2e8f0;
    line-height: 1.7;
    white-space: pre-wrap;
    font-size: 14px;
}
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 12px;
    margin-top: 20px;
    padding: 16px;
    background: rgba(255, 255, 255, 0.02);
    border-radius: 12px;
    border: 1px solid rgba(148, 163, 184, 0.1);
}
.stat-item {
    text-align: center;
    padding: 12px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    border: 1px solid rgba(148, 163, 184, 0.1);
}
.stat-value {
    font-size: 20px;
    font-weight: 700;
    color: #3b82f6;
    margin-bottom: 4px;
}
.stat-label {
    font-size: 12px;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.search-section {
    background: linear-gradient(135deg, rgba(15, 23, 42, 0.8), rgba(30, 41, 59, 0.8));
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    border: 1px solid rgba(148, 163, 184, 0.2);
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    align-items: end;
}
.search-input {
    flex: 1;
    min-width: 250px;
}
.user-select {
    min-width: 150px;
}
.download-section {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 24px;
    padding: 16px;
    background: rgba(255, 255, 255, 0.02);
    border-radius: 12px;
    border: 1px solid rgba(148, 163, 184, 0.1);
    flex-wrap: wrap;
    gap: 16px;
}
.download-btn {
    background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
    color: white;
    border: none;
    padding: 12px 24px;
    border-radius: 50px;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.3s ease;
    display: flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
}
.download-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(59, 130, 246, 0.3);
}
.stCode,.st-emotion-cache-139jccg,.e1t4gh342{
  display: none;
}

</style>
"""
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# اجرای رابط کاربری Premium
username = st.session_state.username
role = st.session_state.role

if role == "admin":
    tab1, tab2 = st.tabs(["📓 گزارش من", "👥 گزارش همه کاربران"])

    with tab1:
        admin_history = load_user_history("admin")
        render_premium_history_ui(
            admin_history,
            key_prefix="admin_self",
            empty_message=":mountain: هنوز گزارشی برای نمایش نداری. اولین قله‌ات رو فتح کن! 🏔️",
            show_user_filter=False,
        )

    with tab2:
        res = supabase.table("user_activities").select("*").order("saved_at", desc=True).execute()
        all_history = pd.DataFrame(res.data)

        render_premium_history_ui(
            all_history,
            key_prefix="admin_all",
            empty_message=":mountain: هنوز هیچ کاربری گزارشی ثبت نکرده. منتظر اولین کوهنورد باش! 🏔️",
            show_user_filter=True,
        )

else:
    user_history = load_user_history(username)
    render_premium_history_ui(
        user_history,
        key_prefix=f"user_{username}",
        empty_message=":mountain: هنوز سفری شروع نکرده‌ای. اولین قدمت رو بردار! 🏔️",
        show_user_filter=False,
    )

import os
import logging
import random
import string
from urllib.parse import quote

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== CONFIG ==================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise RuntimeError("ENV TELEGRAM_TOKEN belum di-set!")

BOT_BRAND = "VanzShop.id"

# Domain default dari generator.email (boleh diganti bebas, nanti user bisa /setdomain juga)
DEFAULT_DOMAIN = "buybm.one"  # contoh, ini salah satu domain yang muncul di generator.email
GENERATOR_BASE = "https://generator.email"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ================== HELPER ==================


def get_user_store(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> dict:
    """Data per-user disimpan di bot_data."""
    bot_data = context.application.bot_data
    if "users" not in bot_data:
        bot_data["users"] = {}
    users = bot_data["users"]
    if user_id not in users:
        users[user_id] = {
            "domain": DEFAULT_DOMAIN,
            "current_email": None,
            "stats": {"single_generated": 0, "batch_generated": 0},
            "last_batch": [],
            "await": None,
            "batch_temp": {},
        }
    return users[user_id]


def random_name(length: int = 10) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def sanitize_name(name: str) -> str:
    """Bersihin nama custom jadi local-part yang aman."""
    allowed = string.ascii_lowercase + string.digits + "._"
    name = name.strip().lower().replace(" ", ".")
    cleaned = "".join(ch if ch in allowed else "." for ch in name)
    while ".." in cleaned:
        cleaned = cleaned.replace("..", ".")
    return cleaned.strip(".")


def build_email(local_part: str, domain: str) -> str:
    return f"{local_part}@{domain}"


def build_inbox_link(email: str) -> str:
    """
    Generator.email kasih format:
      https://generator.email/username@mail-temp.com
    Jadi cukup tempel email di path.
    """
    # pakai quote biar aman kalau ada karakter aneh
    encoded = quote(email, safe="@")
    return f"{GENERATOR_BASE}/{encoded}"


# ================== UI COMPONENTS ==================


def main_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📧 Generate 1 Email", callback_data="menu_single")],
            [InlineKeyboardButton("📦 Batch Email", callback_data="menu_batch")],
            [InlineKeyboardButton("📥 Cek Inbox", callback_data="menu_inbox")],
            [InlineKeyboardButton("⚙️ Set Domain", callback_data="menu_set_domain")],
            [InlineKeyboardButton("ℹ️ Info & Stats", callback_data="menu_info")],
        ]
    )


def batch_mode_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎲 Nama Random", callback_data="batch_mode_random")],
            [InlineKeyboardButton("✏️ Nama Custom (kirim list)", callback_data="batch_mode_custom")],
        ]
    )


# ================== HANDLERS ==================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    store = get_user_store(context, user.id)

    text = (
        f"Yo {user.first_name}! 👋\n\n"
        f"Ini bot generator email temp by *{BOT_BRAND}*.\n\n"
        "✨ Fitur:\n"
        "• Generate 1 email cepat\n"
        "• Batch generate banyak email (nama random / custom)\n"
        "• Set domain per user\n"
        "• Cek inbox via generator.email (link langsung)\n\n"
        f"🌐 Domain aktif kamu sekarang: `{store['domain']}`\n\n"
        "Pilih menu di bawah ya 👇"
    )

    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    else:
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def generate_single_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    store = get_user_store(context, user.id)

    local = random_name(10)
    email = build_email(local, store["domain"])

    store["current_email"] = email
    store["stats"]["single_generated"] += 1

    inbox_link = build_inbox_link(email)

    text = (
        "✅ *Email baru berhasil dibuat!*\n\n"
        f"`{email}`\n\n"
        "Email ini diset sebagai *email aktif* kamu.\n"
        "Gunakan untuk daftar/verifikasi apa pun.\n\n"
        "📥 Inbox via generator.email:\n"
        f"{inbox_link}\n\n"
        "_Klik link di atas dari browser kalau mau lihat isi email._"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())


async def ask_batch_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    store = get_user_store(context, user.id)

    store["await"] = "batch_count"
    store["batch_temp"] = {"domain": store["domain"]}

    text = (
        "📦 *Batch Generator*\n\n"
        f"Domain aktif: `{store['domain']}`\n\n"
        "Kamu mau generate berapa email?\n"
        "_Ketik angka antara 1 - 50._"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


async def inbox_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    store = get_user_store(context, user.id)
    email = store.get("current_email")

    if not email:
        text = (
            "❌ Kamu belum punya email aktif.\n\n"
            "Generate dulu lewat menu *📧 Generate 1 Email* atau *📦 Batch Email*."
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
            )
        return

    inbox_link = build_inbox_link(email)

    text = (
        f"📥 *Inbox Email Aktif*\n\n"
        f"Email: `{email}`\n\n"
        "Buka inbox di generator.email lewat link ini:\n"
        f"{inbox_link}\n\n"
        "➕ Tips:\n"
        "• Buka link di browser HP / PC\n"
        "• Kalau mau email baru lagi, tinggal generate dari menu."
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )


async def ask_set_domain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    store = get_user_store(context, user.id)

    store["await"] = "set_domain"

    text = (
        "⚙️ *Set Domain Email*\n\n"
        f"Domain kamu sekarang: `{store['domain']}`\n\n"
        "Balas dengan domain baru.\n"
        "Contoh:\n"
        "`buybm.one`\n"
        "`mail.vanzshop.id` (kalau domain kamu sudah ditambah di generator.email)"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    store = get_user_store(context, user.id)

    stats = store["stats"]
    email = store.get("current_email") or "- belum ada -"

    text = (
        f"ℹ️ *Info Akun Kamu*\n\n"
        f"ID: `{user.id}`\n"
        f"Nama: {user.full_name}\n\n"
        f"👑 Brand bot: *{BOT_BRAND}*\n"
        f"🌐 Domain aktif: `{store['domain']}`\n"
        f"📧 Email aktif: `{email}`\n\n"
        "📊 *Statistik:*\n"
        f"• Single email dibuat: `{stats['single_generated']}`\n"
        f"• Batch email dibuat: `{stats['batch_generated']}` (total item)\n"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )


async def text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle input text sesuai state (set domain, batch count, custom names)."""
    user = update.effective_user
    store = get_user_store(context, user.id)
    await_state = store.get("await")
    text_msg = (update.message.text or "").strip()

    # SET DOMAIN
    if await_state == "set_domain":
        if " " in text_msg or "@" in text_msg or len(text_msg) < 3:
            await update.message.reply_text(
                "❌ Format domain nggak valid. Coba lagi, contoh: `buybm.one`",
                parse_mode="Markdown",
            )
            return

        store["domain"] = text_msg
        store["await"] = None

        await update.message.reply_text(
            f"✅ Domain berhasil diganti ke: `{text_msg}`",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    # BATCH: JUMLAH
    if await_state == "batch_count":
        if not text_msg.isdigit():
            await update.message.reply_text(
                "❌ Tolong kirim angka aja.\nContoh: `5`",
                parse_mode="Markdown",
            )
            return

        count = int(text_msg)
        if not (1 <= count <= 50):
            await update.message.reply_text(
                "❌ Batas generate 1 - 50 email.\nCoba kirim ulang angkanya.",
                parse_mode="Markdown",
            )
            return

        store["batch_temp"]["count"] = count
        store["await"] = None

        await update.message.reply_text(
            f"OK, akan generate `{count}` email.\n\n"
            "Sekarang pilih mode nama:",
            parse_mode="Markdown",
            reply_markup=batch_mode_keyboard(),
        )
        return

    # BATCH: NAMA CUSTOM
    if await_state == "batch_custom_names":
        raw = text_msg
        parts = []
        for line in raw.splitlines():
            parts.extend([p.strip() for p in line.split(",") if p.strip()])

        if not parts:
            await update.message.reply_text(
                "❌ List nama kosong.\nKirim lagi, pisahkan dengan koma atau baris baru.",
            )
            return

        store["batch_temp"]["names"] = parts
        store["await"] = None

        await run_batch_generation(update, context, custom_names=True)
        return

    # KALO GA DALAM STATE APA PUN
    await update.message.reply_text(
        "Gua kurang nangkep pesannya 😅\nPakai menu di bawah aja ya.",
        reply_markup=main_menu_keyboard(),
    )


async def run_batch_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_names: bool = False):
    user = update.effective_user
    store = get_user_store(context, user.id)
    temp = store.get("batch_temp", {})
    domain = temp.get("domain", store["domain"])
    count = temp.get("count", 1)

    emails = []

    if custom_names:
        raw_names = temp.get("names", [])
        if not raw_names:
            await update.message.reply_text(
                "❌ Nama custom kosong. Coba ulang dari menu batch.",
                reply_markup=main_menu_keyboard(),
            )
            return
        for name in raw_names[:count]:
            local = sanitize_name(name)
            if not local:
                local = random_name(8)
            emails.append(build_email(local, domain))
    else:
        for _ in range(count):
            local = random_name(10)
            emails.append(build_email(local, domain))

    store["last_batch"] = emails
    store["current_email"] = emails[0] if emails else store["current_email"]
    store["stats"]["batch_generated"] += len(emails)

    lines = [
        "✅ *Batch email berhasil dibuat!*\n",
        f"Domain: `{domain}`",
        f"Total: `{len(emails)}` email\n",
        "Daftar email:",
    ]
    for i, e in enumerate(emails, start=1):
        lines.append(f"{i}. `{e}`")

    inbox_link = build_inbox_link(store["current_email"]) if store["current_email"] else None

    lines.append(
        "\nEmail aktif kamu sekarang diset ke:\n"
        f"`{store['current_email']}`"
    )
    if inbox_link:
        lines.append(
            "\n📥 Inbox generator.email:\n"
            f"{inbox_link}"
        )

    text = "\n".join(lines)

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = query.from_user
    get_user_store(context, user.id)  # init

    if data == "menu_single":
        await generate_single_email(update, context)
    elif data == "menu_batch":
        await ask_batch_count(update, context)
    elif data == "menu_inbox":
        await inbox_handler(update, context)
    elif data == "menu_set_domain":
        await ask_set_domain(update, context)
    elif data == "menu_info":
        await show_info(update, context)
    elif data == "batch_mode_random":
        await run_batch_generation(update, context, custom_names=False)
    elif data == "batch_mode_custom":
        store = get_user_store(context, user.id)
        store["await"] = "batch_custom_names"
        await query.edit_message_text(
            "✏️ Kirim list nama local-part untuk email.\n"
            "Pisahkan dengan koma atau baris baru.\n\n"
            "Contoh:\n"
            "`akun1, akun2, akun3`\n\n"
            "Jumlah yang dipakai akan menyesuaikan `count` yang tadi kamu isi.",
            parse_mode="Markdown",
        )
    else:
        await query.answer("Perintah tidak dikenal.", show_alert=True)


# ================== MAIN ==================


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("single", generate_single_email))
    app.add_handler(CommandHandler("batch", ask_batch_count))
    app.add_handler(CommandHandler("inbox", inbox_handler))
    app.add_handler(CommandHandler("domain", ask_set_domain))
    app.add_handler(CommandHandler("info", show_info))

    app.add_handler(CallbackQueryHandler(callback_router))

    # text handler (state set_domain, batch_count, batch_custom_names)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_fallback,
        )
    )

    app.run_polling()


if __name__ == "__main__":
    main()

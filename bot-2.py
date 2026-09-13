import re
import logging

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    BOT_TOKEN,
    CHANNEL_ID,
    BOT_USERNAME,
    AVA_COWOK,
    AVA_CEWEK,
    HASHTAG_COWOK,
    HASHTAG_CEWEK,
    ADMIN_IDS,
    RATE_LIMIT_MAX_PER_HOUR,
    RATE_LIMIT_MIN_INTERVAL_SECONDS,
)
import database as db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MENFESS_PATTERN = re.compile(
    r"^\s*#(?P<tag>\w+)\s+@(?P<username>\w+)\s*\n?(?P<pesan>.+)",
    re.DOTALL | re.IGNORECASE,
)

RULES_TEXT = (
    "📜 <b>RULES SUMATERA MENFESS</b>\n\n"
    "1. Dilarang spam\n"
    "2. Dilarang penipuan\n"
    "3. Dilarang mengirim konten seksual\n"
    "4. Dilarang mengancam\n"
    "5. Dilarang melakukan doxing\n"
    "6. Hormati pengguna lain\n"
    "7. Admin berhak menghapus menfess"
)

HELP_TEXT = (
    "📖 <b>CARA MENGGUNAKAN</b>\n\n"
    "Untuk cowok:\n"
    "<code>#sumboy @username pesan</code>\n\n"
    "Untuk cewek:\n"
    "<code>#sumgirl @username pesan</code>\n\n"
    "Contoh:\n"
    "<code>#sumboy @eka\nHai, semangat kuliahnya hari ini! ❤️</code>\n\n"
    "Pengirim tetap anonim bagi penerima. Kalau menfess kamu terdeteksi "
    "melanggar aturan, akan ditinjau admin dulu sebelum tayang."
)

WELCOME_TEXT = (
    "💌 <b>SUMATERA MENFESS</b>\n\n"
    "Selamat datang di SUMATERA Menfess!\n"
    "Kirim pesan secara anonim kepada seseorang di Telegram.\n\n"
    "Gunakan format:\n"
    "<code>#sumboy @username pesan kamu</code>\n"
    "atau\n"
    "<code>#sumgirl @username pesan kamu</code>"
)


def main_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📖 Cara Menggunakan", callback_data="help")],
            [InlineKeyboardButton("📜 Rules", callback_data="rules")],
        ]
    )


def menfess_action_keyboard(menfess_id: int, likes: int = 0):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"❤️ {likes}", callback_data=f"like:{menfess_id}"),
                InlineKeyboardButton(
                    "💬 Balas",
                    url=f"https://t.me/{BOT_USERNAME}?start=reply_{menfess_id}",
                ),
                InlineKeyboardButton("🚩 Report", callback_data=f"report:{menfess_id}"),
            ]
        ]
    )


def build_caption(kategori: str, target_username: str, pesan: str) -> str:
    header = "💙 SUMATERA MENFESS" if kategori == HASHTAG_COWOK else "💗 SUMATERA MENFESS"
    return (
        f"<b>{header}</b>\n\n"
        f"💌 To: @{target_username}\n\n"
        f"{pesan.strip()}\n\n"
        f"─────────────\n"
        f"📩 Kirim menfess: @{BOT_USERNAME}"
    )


def avatar_for(kategori: str) -> str:
    return AVA_COWOK if kategori == HASHTAG_COWOK else AVA_CEWEK


# =======================================================================
# HANDLER USER: /start, /help, /rules
# =======================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username, update.effective_chat.id)

    # Deep-link: /start reply_<menfess_id>  -> masuk mode balas anonim
    if context.args:
        payload = context.args[0]
        if payload.startswith("reply_"):
            try:
                menfess_id = int(payload.split("_", 1)[1])
            except ValueError:
                menfess_id = None
            if menfess_id and db.get_menfess(menfess_id):
                context.user_data["replying_to"] = menfess_id
                await update.message.reply_text(
                    "💬 Ketik balasan kamu untuk menfess tersebut. "
                    "Identitas kamu tidak akan ditampilkan."
                )
                return

    if db.is_banned(user.id):
        await update.message.reply_text(
            "🚫 Akun kamu diblokir dari layanan ini karena melanggar aturan."
        )
        return

    await update.message.reply_text(
        WELCOME_TEXT, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES_TEXT, parse_mode=ParseMode.HTML)


# =======================================================================
# HANDLER UTAMA: kirim menfess ATAU balas menfess (private text message)
# =======================================================================

async def handle_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    text = message.text

    if not text:
        return

    # Mode balas menfess (state disimpan sejak deep-link /start reply_<id>)
    replying_to = context.user_data.get("replying_to")
    if replying_to:
        await _send_reply(update, context, replying_to, text)
        context.user_data.pop("replying_to", None)
        return

    await _handle_new_menfess(update, context, text)


async def _send_reply(update, context, menfess_id: int, reply_text: str):
    menfess = db.get_menfess(menfess_id)
    if not menfess:
        await update.message.reply_text("Menfess tidak ditemukan (mungkin sudah dihapus).")
        return

    sender = db.get_user_by_telegram_id(menfess["sender_id"])
    if not sender or not sender.get("chat_id"):
        await update.message.reply_text(
            "Maaf, pengirim menfess ini belum bisa dikirimi balasan."
        )
        return

    try:
        await context.bot.send_message(
            chat_id=sender["chat_id"],
            text=(
                "💌 <b>Ada balasan untuk menfess kamu:</b>\n\n"
                f"\"{reply_text.strip()}\""
            ),
            parse_mode=ParseMode.HTML,
        )
        await update.message.reply_text("✅ Balasan kamu sudah terkirim secara anonim.")
    except Forbidden:
        await update.message.reply_text(
            "Maaf, balasan gagal terkirim (pengirim memblokir bot)."
        )


async def _handle_new_menfess(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    message = update.message
    user = update.effective_user

    if db.is_banned(user.id):
        await message.reply_text("🚫 Akun kamu diblokir dan tidak bisa mengirim menfess.")
        return

    match = MENFESS_PATTERN.match(text)
    if not match:
        await message.reply_text(
            "Format tidak dikenali. Gunakan:\n\n"
            "#sumboy @username\n<isi pesan>\n\n"
            "atau\n\n"
            "#sumgirl @username\n<isi pesan>\n\n"
            "Ketik /help untuk contoh lengkap."
        )
        return

    tag = match.group("tag").lower()
    target_username = match.group("username")
    pesan = match.group("pesan").strip()

    if tag == HASHTAG_COWOK:
        kategori = HASHTAG_COWOK
    elif tag == HASHTAG_CEWEK:
        kategori = HASHTAG_CEWEK
    else:
        await message.reply_text(f"Hashtag #{tag} tidak dikenali. Gunakan #sumboy atau #sumgirl.")
        return

    if not pesan:
        await message.reply_text("Isi pesan tidak boleh kosong.")
        return

    # ---- anti-spam ----
    recent_count = db.count_recent_by_sender(user.id, minutes=60)
    if recent_count >= RATE_LIMIT_MAX_PER_HOUR:
        await message.reply_text(
            f"⏳ Kamu sudah mengirim {recent_count} menfess dalam 1 jam terakhir. "
            f"Coba lagi nanti ya (maks {RATE_LIMIT_MAX_PER_HOUR}/jam)."
        )
        return

    seconds_since_last = db.seconds_since_last_sent(user.id)
    if seconds_since_last is not None and seconds_since_last < RATE_LIMIT_MIN_INTERVAL_SECONDS:
        sisa = int(RATE_LIMIT_MIN_INTERVAL_SECONDS - seconds_since_last)
        await message.reply_text(f"⏳ Tunggu {sisa} detik lagi sebelum kirim menfess berikutnya.")
        return

    menfess_id = db.create_menfess(
        sender_id=user.id,
        sender_username=user.username,
        receiver_username=target_username,
        kategori=kategori,
        pesan=pesan,
        status="terkirim",
    )

    await _publish_menfess(context, menfess_id, kategori, target_username, pesan)
    await message.reply_text("✅ Menfess kamu berhasil dikirim!")


async def _publish_menfess(context, menfess_id, kategori, target_username, pesan):
    """Kirim menfess ke channel, dan kalau penerima sudah pernah /start bot,
    kirim juga salinan anonimnya lewat DM."""
    caption = build_caption(kategori, target_username, pesan)
    avatar_path = avatar_for(kategori)
    keyboard = menfess_action_keyboard(menfess_id, likes=0)

    try:
        with open(avatar_path, "rb") as photo:
            sent = await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        db.set_channel_message_id(menfess_id, sent.message_id)
    except FileNotFoundError:
        logger.error("File avatar tidak ditemukan: %s", avatar_path)
    except Exception:
        logger.exception("Gagal mengirim menfess ke channel")

    receiver = db.get_user_by_username(target_username)
    if receiver and receiver.get("chat_id"):
        dm_text = (
            "💌 <b>SUMATERA MENFESS</b>\n\n"
            "Ada seseorang yang mengirimkan menfess untukmu:\n\n"
            f"\"{pesan.strip()}\""
        )
        try:
            await context.bot.send_message(
                chat_id=receiver["chat_id"],
                text=dm_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        except Forbidden:
            logger.info("Tidak bisa DM penerima @%s (memblokir bot)", target_username)

    db.update_menfess_status(menfess_id, "terkirim")





# =======================================================================
# CALLBACK QUERY: like, report, menu help/rules, aksi admin
# =======================================================================

REPORT_REASONS = {
    "spam": "Spam",
    "sexual": "Konten seksual",
    "harassment": "Pelecehan/kata kasar",
    "other": "Lainnya",
}


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = update.effective_user

    if data == "help":
        await query.answer()
        await query.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)
        return

    if data == "rules":
        await query.answer()
        await query.message.reply_text(RULES_TEXT, parse_mode=ParseMode.HTML)
        return

    if data.startswith("like:"):
        menfess_id = int(data.split(":", 1)[1])
        new_likes = db.increment_like(menfess_id)
        await query.answer(f"❤️ Like ({new_likes})")
        try:
            await query.edit_message_reply_markup(
                reply_markup=menfess_action_keyboard(menfess_id, likes=new_likes)
            )
        except BadRequest:
            pass
        return

    if data.startswith("report:"):
        menfess_id = int(data.split(":", 1)[1])
        await query.answer()
        reason_keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(label, callback_data=f"reportreason:{menfess_id}:{code}")]
                for code, label in REPORT_REASONS.items()
            ]
        )
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="🚩 Kenapa kamu melaporkan menfess ini?",
                reply_markup=reason_keyboard,
            )
        except Forbidden:
            await query.answer(
                url=f"https://t.me/{BOT_USERNAME}?start=start",
                text="Buka chat bot dulu untuk melapor.",
                show_alert=True,
            )
        return

    if data.startswith("reportreason:"):
        _, menfess_id_str, code = data.split(":")
        menfess_id = int(menfess_id_str)
        reason_label = REPORT_REASONS.get(code, "Lainnya")
        db.create_report(menfess_id, user.id, reason_label)
        await query.answer("Laporan terkirim, terima kasih 🙏")
        await query.edit_message_text("✅ Laporan kamu sudah dikirim ke admin untuk ditinjau.")
        await _notify_admins_report(context, menfess_id, user, reason_label)
        return

    # ---- aksi admin ----
    if data.startswith("adm_approve:"):
        await _admin_approve(query, context, int(data.split(":", 1)[1]))
        return

    if data.startswith("adm_delete:"):
        await _admin_delete(query, context, int(data.split(":", 1)[1]))
        return

    if data.startswith("adm_ban:"):
        await _admin_ban(query, context, int(data.split(":", 1)[1]))
        return

    if data.startswith("adm_unban:"):
        telegram_id = int(data.split(":", 1)[1])
        db.unban_user(telegram_id)
        await query.answer("User di-unban")
        await query.edit_message_text(f"✅ User {telegram_id} sudah di-unban.")
        return

    if data == "admin:stats":
        await query.answer()
        await query.edit_message_text(_stats_text(), parse_mode=ParseMode.HTML,
                                       reply_markup=admin_menu_keyboard())
        return

    if data == "admin:reports":
        await query.answer()
        await query.edit_message_text(_pending_reports_text(), parse_mode=ParseMode.HTML,
                                       reply_markup=admin_menu_keyboard())
        return

    if data == "admin:banned":
        await query.answer()
        await _show_banned_list(query)
        return

    if data == "admin:menu":
        await query.answer()
        await query.edit_message_text("👑 <b>ADMIN PANEL</b>", parse_mode=ParseMode.HTML,
                                       reply_markup=admin_menu_keyboard())
        return


async def _notify_admins_report(context, menfess_id, reporter, reason_label):
    menfess = db.get_menfess(menfess_id)
    if not menfess or not ADMIN_IDS:
        return
    text = (
        f"🚩 <b>REPORT BARU</b> (menfess #{menfess_id})\n\n"
        f"Alasan: {reason_label}\n"
        f"Pelapor ID internal: {reporter.id}\n\n"
        f"Isi menfess:\n\"{menfess['pesan']}\""
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🗑️ Delete", callback_data=f"adm_delete:{menfess_id}"),
                InlineKeyboardButton("🚫 Ban Sender", callback_data=f"adm_ban:{menfess_id}"),
            ]
        ]
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text,
                                             parse_mode=ParseMode.HTML, reply_markup=keyboard)
        except Forbidden:
            pass


# =======================================================================
# ADMIN: aksi approve/delete/ban dari notifikasi pending
# =======================================================================

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def _admin_approve(query, context, menfess_id: int):
    if not _is_admin(query.from_user.id):
        await query.answer("Kamu bukan admin.", show_alert=True)
        return
    menfess = db.get_menfess(menfess_id)
    if not menfess:
        await query.answer("Menfess tidak ditemukan.", show_alert=True)
        return
    await _publish_menfess(context, menfess_id, menfess["kategori"],
                            menfess["receiver_username"], menfess["pesan"])
    await query.answer("Disetujui & dipublikasikan")
    await query.edit_message_text(f"✅ Menfess #{menfess_id} disetujui dan sudah tayang di channel.")
    sender = db.get_user_by_telegram_id(menfess["sender_id"])
    if sender and sender.get("chat_id"):
        try:
            await context.bot.send_message(
                chat_id=sender["chat_id"],
                text="✅ Menfess kamu sudah disetujui admin dan sekarang tayang di channel.",
            )
        except Forbidden:
            pass


async def _admin_delete(query, context, menfess_id: int):
    if not _is_admin(query.from_user.id):
        await query.answer("Kamu bukan admin.", show_alert=True)
        return
    menfess = db.get_menfess(menfess_id)
    if not menfess:
        await query.answer("Menfess tidak ditemukan.", show_alert=True)
        return
    db.update_menfess_status(menfess_id, "dihapus")
    await query.answer("Menfess dihapus")
    await query.edit_message_text(f"🗑️ Menfess #{menfess_id} dihapus.")
    sender = db.get_user_by_telegram_id(menfess["sender_id"])
    if sender and sender.get("chat_id"):
        try:
            await context.bot.send_message(
                chat_id=sender["chat_id"],
                text="🗑️ Menfess kamu ditolak admin karena melanggar aturan.",
            )
        except Forbidden:
            pass


async def _admin_ban(query, context, menfess_id: int):
    if not _is_admin(query.from_user.id):
        await query.answer("Kamu bukan admin.", show_alert=True)
        return
    menfess = db.get_menfess(menfess_id)
    if not menfess:
        await query.answer("Menfess tidak ditemukan.", show_alert=True)
        return
    db.ban_user(menfess["sender_id"])
    db.update_menfess_status(menfess_id, "dihapus")
    await query.answer("User di-ban")
    await query.edit_message_text(
        f"🚫 Pengirim menfess #{menfess_id} sudah di-ban dan tidak bisa kirim menfess lagi."
    )


# =======================================================================
# ADMIN PANEL: /admin, /broadcast
# =======================================================================

def admin_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 Statistik", callback_data="admin:stats")],
            [InlineKeyboardButton("🚩 Reports", callback_data="admin:reports")],
            [InlineKeyboardButton("🚫 Banned Users", callback_data="admin:banned")],
        ]
    )


def _stats_text() -> str:
    return (
        "📊 <b>STATISTIK</b>\n\n"
        f"👤 Total Users: {db.count_users()}\n"
        f"📩 Total Menfess: {db.count_menfess_total()}\n"
        f"🚩 Reports: {db.count_reports_total()}\n"
        f"🚫 Banned: {db.count_banned_total()}\n\n"
        f"📅 Hari ini:\n"
        f"👤 User baru: {db.count_new_users_today()}\n"
        f"📩 Menfess: {db.count_menfess_today()}"
    )


def _pending_reports_text() -> str:
    reports = db.list_pending_reports()
    if not reports:
        return "🚩 <b>REPORTS</b>\n\nTidak ada laporan pending saat ini."
    lines = ["🚩 <b>REPORTS PENDING</b>\n"]
    for r in reports[:15]:
        lines.append(f"#{r['id']} — menfess #{r['menfess_id']} — {r['reason']}")
    if len(reports) > 15:
        lines.append(f"\n...dan {len(reports) - 15} laporan lainnya.")
    return "\n".join(lines)


async def _show_banned_list(query):
    banned = db.list_banned_users()
    if not banned:
        await query.edit_message_text("🚫 Tidak ada user yang di-ban saat ini.",
                                        reply_markup=admin_menu_keyboard())
        return
    keyboard_rows = [
        [InlineKeyboardButton(f"Unban @{u['username'] or u['telegram_id']}",
                               callback_data=f"adm_unban:{u['telegram_id']}")]
        for u in banned[:20]
    ]
    keyboard_rows.append([InlineKeyboardButton("⬅️ Kembali", callback_data="admin:menu")])
    await query.edit_message_text(
        f"🚫 <b>BANNED USERS</b> ({len(banned)})", parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Perintah ini khusus admin.")
        return
    await update.message.reply_text("👑 <b>ADMIN PANEL</b>", parse_mode=ParseMode.HTML,
                                     reply_markup=admin_menu_keyboard())


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Perintah ini khusus admin.")
        return
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Format: /broadcast <pesan pengumuman>")
        return

    chat_ids = db.list_all_chat_ids()
    sent, failed = 0, 0
    for chat_id in chat_ids:
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=f"📢 <b>PENGUMUMAN</b>\n\n{text}", parse_mode=ParseMode.HTML
            )
            sent += 1
        except Forbidden:
            failed += 1
    await update.message.reply_text(f"Broadcast selesai. Terkirim: {sent}, gagal: {failed}.")


# =======================================================================
# MAIN
# =======================================================================

def main():
    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rules", rules_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_private_text))

    logger.info("Bot berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()

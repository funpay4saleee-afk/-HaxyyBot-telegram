import os
import asyncio
import aiohttp
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = "8953907801:AAHR9yG31Am46KjvNLAGS8c2rtJ1GxLNBzs"
GROQ_KEY = "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"
DOWNLOAD_PATH = "/sdcard/Download/bot_media"
CACHE_PATH = "/sdcard/Download/bot_cache"
STATS_FILE = "/sdcard/Download/bot_stats.json"
LOGS_FILE = "/sdcard/Download/bot_logs.json"

SUPPORTED_SITES = [
    "youtube.com", "youtu.be", "music.youtube.com",
    "tiktok.com", "vt.tiktok.com",
    "instagram.com",
    "vk.com", "vkvideo.ru",
    "twitter.com", "x.com"
]

pending_requests = {}
ADMIN_ID = 7326782020

def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def add_point(username):
    stats = load_json(STATS_FILE)
    stats[username] = stats.get(username, 0) + 1
    save_json(STATS_FILE, stats)

def add_log(user_id, username, url, quality):
    logs = load_json(LOGS_FILE)
    if "history" not in logs:
        logs["history"] = []
    logs["history"].append({
        "user_id": user_id,
        "user": username,
        "url": url,
        "quality": quality,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_json(LOGS_FILE, logs)

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я HaxyyBot.\nКидай ссылку — скачаю.\n/ai вопрос — нейросеть\n/stats — топ")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = load_json(STATS_FILE)
    if not stats:
        await update.message.reply_text("🏆 Топ пока пуст.")
        return
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    text = "🏆 Топ пользователей:\n\n"
    for i, (user, points) in enumerate(sorted_stats[:10], 1):
        text += f"{i}. {user} — {points} скачиваний\n"
    await update.message.reply_text(text)

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    logs = load_json(LOGS_FILE).get("history", [])
    if not logs:
        await update.message.reply_text("📋 История пуста.")
        return
    text = "📋 Последние 20:\n\n"
    shown = 0
    for log in reversed(logs):
        if log.get("user_id") == ADMIN_ID:
            continue
        text += f"👤 {log['user']}\n🔗 {log['url'][:50]}...\n🎬 {log['quality']}\n🕒 {log['time']}\n\n"
        shown += 1
        if shown >= 20:
            break
    if shown == 0:
        text += "(только ваши действия)"
    await update.message.reply_text(text)

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Напиши вопрос. Например: /ai рецепт оладьев")
        return
    
    question = " ".join(context.args)
    status_msg = await update.message.reply_text("🤔 Думаю...")
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": question}],
                "temperature": 0.7
            }
            async with session.post("https://api.groq.com/openai/v1/chat/completions", json=data, headers=headers) as resp:
                result = await resp.json()
                if "choices" in result:
                    answer = result["choices"][0]["message"]["content"]
                    await status_msg.edit_text(answer[:4000])
                else:
                    await status_msg.edit_text(f"❌ Ошибка: {result}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")

async def download_file(url, file_name):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                with open(file_name, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        f.write(chunk)
                return True
    return False

async def show_animation(msg, text):
    frames = ["⏳", "⌛"]
    dots = 0
    frame_idx = 0
    async def animate():
        nonlocal dots, frame_idx
        while True:
            frame_idx = (frame_idx + 1) % 2
            dots = (dots + 1) % 4
            try:
                await msg.edit_text(f"{frames[frame_idx]} {text}{'.' * dots}{' ' * (3 - dots)}")
            except:
                pass
            await asyncio.sleep(0.5)
    task = asyncio.create_task(animate())
    return task

async def get_video_title(url):
    cmd = ["yt-dlp", "--get-title", "--no-playlist", url]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5)
        if process.returncode == 0:
            return stdout.decode().strip()
    except:
        pass
    return "YouTube Audio"

async def handle_mp3(update, context, url, user_id, chat_id, message):
    username = message.from_user.username or message.from_user.first_name
    if not os.path.exists(DOWNLOAD_PATH):
        os.makedirs(DOWNLOAD_PATH)
    
    status_msg = await message.reply_text("⏳ Скачиваю MP3")
    anim_task = await show_animation(status_msg, "Скачиваю MP3")
    
    title = await get_video_title(url)
    video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1]
    api_url = f"https://api.vevioz.com/@api/button/mp3/{video_id}"
    
    downloaded = False
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api_url, timeout=10) as resp:
                data = await resp.json()
                if data.get("success") and data.get("link"):
                    mp3_url = data["link"]
                    final_mp3 = os.path.join(DOWNLOAD_PATH, f"{video_id}.mp3")
                    if await download_file(mp3_url, final_mp3):
                        downloaded = True
                        anim_task.cancel()
                        try: await anim_task
                        except: pass
                        await context.bot.send_audio(
                            chat_id=chat_id,
                            audio=open(final_mp3, "rb"),
                            title=title,
                            performer="@HaxyyBot"
                        )
                        os.remove(final_mp3)
        except:
            pass
    
    if not downloaded:
        final_mp3 = os.path.join(DOWNLOAD_PATH, "final_audio.mp3")
        cmd = [
            "yt-dlp",
            "-x", "--audio-format", "mp3", "--audio-quality", "0",
            "-o", final_mp3,
            "--no-playlist",
            "--no-check-certificates",
            "-N", "8",
            url
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await asyncio.wait_for(process.communicate(), timeout=60)
            if process.returncode == 0 and os.path.exists(final_mp3):
                anim_task.cancel()
                try: await anim_task
                except: pass
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=open(final_mp3, "rb"),
                    title=title,
                    performer="@HaxyyBot"
                )
                os.remove(final_mp3)
                downloaded = True
        except:
            pass
    
    anim_task.cancel()
    try: await anim_task
    except: pass
    
    if downloaded:
        add_point(username)
        add_log(user_id, username, url, "MP3")
        await status_msg.delete()
        await context.bot.send_message(chat_id=chat_id, text="✅ Готово!")
    else:
        await status_msg.edit_text("❌ Ошибка")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Проверяем, является ли сообщение ссылкой
    if not (url.startswith("http") and any(site in url for site in SUPPORTED_SITES)):
        # Не ссылка — игнорируем
        return

    if "music.youtube.com" in url:
        await handle_mp3(update, context, url, user_id, chat_id, update.message)
        return

    if "youtube.com" in url or "youtu.be" in url:
        pending_requests[user_id] = url
        keyboard = [
            [InlineKeyboardButton("🎬 Видео", callback_data="video")],
            [InlineKeyboardButton("🎵 MP3", callback_data="mp3")]
        ]
        await update.message.reply_text("Что качать?", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if not os.path.exists(DOWNLOAD_PATH):
        os.makedirs(DOWNLOAD_PATH)

    if "tiktok.com" in url:
        pending_requests[user_id] = url
        keyboard = [
            [InlineKeyboardButton("🎬 Видео", callback_data="tiktok_video")],
            [InlineKeyboardButton("🎵 Звук", callback_data="tiktok_audio")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
        ]
        await update.message.reply_text("Что качать?", reply_markup=InlineKeyboardMarkup(keyboard))
        return

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data
    username = query.from_user.username or query.from_user.first_name

    if data == "cancel":
        if user_id in pending_requests:
            del pending_requests[user_id]
        await query.edit_message_text("🚫 Отменено.")
        return

    if data in ["tiktok_video", "tiktok_audio"]:
        if user_id not in pending_requests:
            await query.edit_message_text("❌ Ссылка устарела.")
            return
        url = pending_requests.pop(user_id)
        if not os.path.exists(DOWNLOAD_PATH):
            os.makedirs(DOWNLOAD_PATH)
        
        status_msg = await query.message
        anim_task = await show_animation(status_msg, "Скачиваю")
        
        api_url = f"https://tikwm.com/api/?url={url}"
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                tiktok_data = await resp.json()
                anim_task.cancel()
                try: await anim_task
                except: pass
                
                if tiktok_data.get("code") != 0:
                    await status_msg.edit_text("❌ Ошибка")
                    return
                if data == "tiktok_video":
                    video_url = tiktok_data["data"]["play"]
                    file_name = os.path.join(DOWNLOAD_PATH, f"tiktok_{tiktok_data['data']['id']}.mp4")
                    if await download_file(video_url, file_name):
                        await context.bot.send_video(chat_id=chat_id, video=open(file_name, "rb"), supports_streaming=True)
                        os.remove(file_name)
                        add_point(username)
                        add_log(user_id, username, url, "TikTok")
                        await status_msg.delete()
                        await context.bot.send_message(chat_id=chat_id, text="✅ Готово!")
                else:
                    audio_url = tiktok_data["data"]["music"]
                    file_name = os.path.join(DOWNLOAD_PATH, f"tiktok_{tiktok_data['data']['id']}.mp3")
                    if await download_file(audio_url, file_name):
                        await context.bot.send_audio(
                            chat_id=chat_id,
                            audio=open(file_name, "rb"),
                            title=tiktok_data["data"]["title"],
                            performer="@HaxyyBot"
                        )
                        os.remove(file_name)
                        add_point(username)
                        add_log(user_id, username, url, "TikTok звук")
                        await status_msg.delete()
                        await context.bot.send_message(chat_id=chat_id, text="✅ Готово!")
        return

    if user_id not in pending_requests:
        await query.edit_message_text("❌ Ссылка устарела.")
        return

    url = pending_requests.pop(user_id)

    if data == "mp3":
        await handle_mp3(update, context, url, user_id, chat_id, query.message)
        return

    if data == "video":
        if not os.path.exists(DOWNLOAD_PATH):
            os.makedirs(DOWNLOAD_PATH)
        if not os.path.exists(CACHE_PATH):
            os.makedirs(CACHE_PATH)

        cache_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1]
        cache_file = os.path.join(CACHE_PATH, f"{cache_id}.mp4")
        if os.path.exists(cache_file):
            await context.bot.send_video(chat_id=chat_id, video=open(cache_file, "rb"), supports_streaming=True)
            add_point(username)
            add_log(user_id, username, url, "Видео (кэш)")
            await query.message.delete()
            await context.bot.send_message(chat_id=chat_id, text="✅ Готово (кэш)!")
            return

        status_msg = await query.message
        anim_task = await show_animation(status_msg, "Скачиваю видео")
        
        output = os.path.join(DOWNLOAD_PATH, "%(title)s.%(ext)s")
        cmd = [
            "yt-dlp",
            "-f", "bestvideo+bestaudio",
            "--merge-output-format", "mp4",
            "-o", output,
            "--no-playlist",
            "--no-check-certificates",
            "-N", "8",
            url
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await asyncio.wait_for(process.communicate(), timeout=60)
            anim_task.cancel()
            try: await anim_task
            except: pass
            
            if process.returncode != 0:
                await status_msg.edit_text("❌ Ошибка")
                return
            
            files = os.listdir(DOWNLOAD_PATH)
            if not files:
                await status_msg.edit_text("❌ Файл не найден.")
                return
            
            latest = max([os.path.join(DOWNLOAD_PATH, f) for f in files], key=os.path.getctime)
            if os.path.getsize(latest) > 50 * 1024 * 1024:
                await status_msg.edit_text("❌ >50 МБ")
                os.remove(latest)
                return
            
            os.rename(latest, cache_file)
            await context.bot.send_video(chat_id=chat_id, video=open(cache_file, "rb"), supports_streaming=True)
            add_point(username)
            add_log(user_id, username, url, "Видео")
            await status_msg.delete()
            await context.bot.send_message(chat_id=chat_id, text="✅ Готово!")
        except asyncio.TimeoutError:
            anim_task.cancel()
            try: await anim_task
            except: pass
            await status_msg.edit_text("❌ Тайм-аут")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("ai", ai_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("✅ HaxyyBot v39 (только ссылки и команды) запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()

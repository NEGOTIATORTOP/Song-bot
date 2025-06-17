import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile, InlineQueryResultAudio
from yt_dlp import YoutubeDL
from lyricsgenius import Genius
import sqlite3

TELEGRAM_TOKEN = os.getenv('7726370542:AAEFlac-cTcHTdHVQDJwsKM6ghZxD0pEkoc')
GENIUS_TOKEN = os.getenv('U2di8TjcZxARQCiVzcF9Yh2jZtW6ofWsmFePf0N2w0vfLxpIVy')

logging.basicConfig(level=logging.INFO)
bot = Bot(token="7726370542:AAEFlac-cTcHTdHVQDJwsKM6ghZxD0pEkoc")
dp7 = Dispatcher()
genius = Genius("U2di8TjcZxARQCiVzcF9Yh2jZtW6ofWsmFePf0N2w0vfLxpIVy", skip_non_songs=True, excluded_terms=["(Remix)", "(Live)"])

conn = sqlite3.connect("musicbot.db")
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS favorites (user_id INTEGER, title TEXT, url TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS history (user_id INTEGER, title TEXT, url TEXT)")
conn.commit()

YDL_OPTS = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'noplaylist': True,
    'quiet': True,
    'extractaudio': True,
    'audioformat': 'mp3',
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'no_warnings': True,
    'default_search': 'ytsearch1',
    'source_address': '0.0.0.0',
}

queues = {}
repeat_flags = {}
admin_only = {}
now_playing = {}

def ensure_download_dir():
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

def db_add_favorite(user_id, title, url):
    cur.execute("INSERT INTO favorites (user_id, title, url) VALUES (?, ?, ?)", (user_id, title, url))
    conn.commit()

def db_list_favorites(user_id):
    cur.execute("SELECT title, url FROM favorites WHERE user_id = ?", (user_id,))
    return cur.fetchall()

def db_add_history(user_id, title, url):
    cur.execute("INSERT INTO history (user_id, title, url) VALUES (?, ?, ?)", (user_id, title, url))
    conn.commit()

def db_list_history(user_id):
    cur.execute("SELECT title, url FROM history WHERE user_id = ? ORDER BY rowid DESC LIMIT 10", (user_id,))
    return cur.fetchall()

async def download_audio(query):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _download_audio, query)

def _download_audio(query):
    with YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(query, download=True)
        if not info:
            return None, None, None, None, None
        if 'entries' in info:
            info = info['entries'][0]
        filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
        if not os.path.exists(filename):
            fallback = ydl.prepare_filename(info)
            if os.path.exists(fallback):
                filename = fallback
            else:
                return None, None, None, None, None
        title = info.get('title', 'Unknown Title')
        url = info.get('webpage_url', '')
        duration = info.get('duration', 0)
        thumb = info.get('thumbnail')
        return filename, title, url, duration, thumb

def get_queue_text(chat_id):
    queue = queues.get(chat_id, [])
    if not queue:
        return None
    text = ""
    for idx, song in enumerate(queue):
        text += f"{idx+1}. {song['title']} ({song['duration']//60}:{song['duration']%60:02})\n"
    return text

def get_nowplaying_text(chat_id):
    song = now_playing.get(chat_id)
    if not song:
        return None
    return f"{song['title']} ({song['duration']//60}:{song['duration']%60:02})\n<a href='{song['url']}'>[YouTube]</a>"

def is_admin(user, chat):
    if chat.type == "private":
        return True
    return True  # For demo purposes

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer(
        "🎵 Yo! Welcome to your 🔥 High-End Music Bot! Let's vibe with some real bangers! Type /play <song> to get started 🎧✨"
    )

@dp.message(Command("play"))
async def play_handler(message: types.Message, command: CommandObject):
    chat_id = message.chat.id
    query = command.args
    if not query:
        await message.reply("❓ Usage: /play <song>")
        return
    if admin_only.get(chat_id) and not is_admin(message.from_user, message.chat):
        await message.reply("🔒 Yo! Only admins got the aux now 🔌 Don’t mess with the vibe 🔥")
        return
    await message.reply(f"🎶 Searching for <b>{query}</b>... Gimme a sec while I fetch the beat! 🕺💿", parse_mode='HTML')
    ensure_download_dir()
    filename, title, url, duration, thumb = await download_audio(query)
    if not filename:
        await message.reply("❌ Uh-oh! Couldn’t find that jam 😢 Try another title, maybe?")
        return
    queues.setdefault(chat_id, []).append({'title': title, 'filename': filename, 'url': url, 'duration': duration, 'thumb_url': thumb})
    db_add_history(message.from_user.id, title, url)
    if chat_id not in now_playing:
        await play_next_in_queue(message, chat_id)
    else:
        await message.reply(f"✅ Boom! <b>{title}</b> dropped into the queue, homie! Let’s get this party lit 🔥🎉", parse_mode='HTML')

async def play_next_in_queue(message, chat_id):
    queue = queues.get(chat_id, [])
    if not queue:
        now_playing.pop(chat_id, None)
        await message.reply("✅ Queue finished.")
        return
    song = queue.pop(0)
    now_playing[chat_id] = song
    await message.answer_audio(
        FSInputFile(song['filename']),
        title=song['title'],
        caption=f"🎧 Vibin' right now to:\n{song['title']} 🔥",
        parse_mode='HTML',
        thumbnail=song.get('thumb_url') if song.get('thumb_url') else None
    )
    try:
        os.remove(song['filename'])
    except Exception:
        pass
    if repeat_flags.get(chat_id):
        queue.append(song)
    await asyncio.sleep(1)
    now_playing.pop(chat_id, None)
    if queue:
        await play_next_in_queue(message, chat_id)
    queues[chat_id] = queue

@dp.message(Command("pause"))
async def pause_handler(message: types.Message):
    await message.reply("⏸️ Chill pill taken 😎 Music paused... but we’ll be back in a beat!")

@dp.message(Command("resume"))
async def resume_handler(message: types.Message):
    await message.reply("▶️ Let’s gooo! Droppin’ back in with the beat 🎶🔥")

@dp.message(Command("stop"))
async def stop_handler(message: types.Message):
    chat_id = message.chat.id
    if admin_only.get(chat_id) and not is_admin(message.from_user, message.chat):
        await message.reply("🔒 Yo! Only admins got the aux now 🔌 Don’t mess with the vibe 🔥")
        return
    queues[chat_id] = []
    now_playing.pop(chat_id, None)
    await message.reply("🛑 Whoa there! Playback stopped and queue cleared 💥 Back to silence... for now 😅")

@dp.message(Command("skip"))
async def skip_handler(message: types.Message):
    chat_id = message.chat.id
    if admin_only.get(chat_id) and not is_admin(message.from_user, message.chat):
        await message.reply("🔒 Yo! Only admins got the aux now 🔌 Don’t mess with the vibe 🔥")
        return
    await message.reply("⏭️ Skipping the current vibe... Loading the next banger 🎧⏩")
    await play_next_in_queue(message, chat_id)

@dp.message(Command("queue"))
async def queue_handler(message: types.Message):
    chat_id = message.chat.id
    queue_txt = get_queue_text(chat_id)
    if queue_txt:
        await message.reply(f"📋 Here’s what’s lined up, chief:\n{queue_txt}")
    else:
        await message.reply("🎵 Queue’s empty right now 😢 Drop some tracks with /play!")

@dp.message(Command("nowplaying"))
async def nowplaying_handler(message: types.Message):
    chat_id = message.chat.id
    nowplaying_txt = get_nowplaying_text(chat_id)
    if nowplaying_txt:
        await message.reply(f"🎧 Vibin' right now to:\n{nowplaying_txt} 🔥", parse_mode='HTML', disable_web_page_preview=False)
    else:
        await message.reply("🤷‍♂️ Nothin' playin’ right now, bruh. Drop a track!")

@dp.message(Command("shuffle"))
async def shuffle_handler(message: types.Message):
    import random
    chat_id = message.chat.id
    queue = queues.get(chat_id, [])
    random.shuffle(queue)
    queues[chat_id] = queue
    await message.reply("🔀 Woo! Shuffled the queue like a DJ 🎛️ Let’s spice it up 💃🕺")

@dp.message(Command("repeat"))
async def repeat_handler(message: types.Message):
    chat_id = message.chat.id
    repeat_flags[chat_id] = not repeat_flags.get(chat_id, False)
    if repeat_flags[chat_id]:
        await message.reply("🔁 Yo, Repeat mode ON! This one’s a banger, let it ride again! 🚗🎶")
    else:
        await message.reply("⏹️ Repeat turned OFF. One ride only 🚫")

@dp.message(Command("remove"))
async def remove_handler(message: types.Message, command: CommandObject):
    chat_id = message.chat.id
    queue = queues.get(chat_id, [])
    try:
        idx = int(command.args.strip()) - 1
        removed = queue.pop(idx)
        queues[chat_id] = queue
        await message.reply(f"🗑️ Boom! <b>{removed['title']}</b> kicked from the queue 💥 Who needs it anyway 😜", parse_mode='HTML')
    except Exception:
        await message.reply("❓ Bro, you gotta tell me which one to remove like this: /remove <position> 🤓")

@dp.message(Command("move"))
async def move_handler(message: types.Message, command: CommandObject):
    chat_id = message.chat.id
    queue = queues.get(chat_id, [])
    try:
        parts = command.args.strip().split()
        from_idx = int(parts[0]) - 1
        to_idx = int(parts[1]) - 1
        song = queue.pop(from_idx)
        queue.insert(to_idx, song)
        queues[chat_id] = queue
        await message.reply(f"➡️ Moved <b>{song['title']}</b> to position {to_idx+1}. DJ moves 😎🎚️", parse_mode='HTML')
    except Exception:
        await message.reply("❓ Usage: /move <from> <to>. Help me help you, mate 😅")

@dp.message(Command("adminonly"))
async def adminonly_handler(message: types.Message):
    chat_id = message.chat.id
    admin_only[chat_id] = not admin_only.get(chat_id, False)
    if admin_only[chat_id]:
        await message.reply("🔒 Yo! Only admins got the aux now 🔌 Don’t mess with the vibe 🔥")
    else:
        await message.reply("🔓 Open house! Anyone can vibe and control now 🎉👐")

@dp.message(Command("favorites"))
async def favorites_handler(message: types.Message):
    favs = db_list_favorites(message.from_user.id)
    if not favs:
        await message.reply("😢 No favorites yet, bro. Use /addfavorite to save some gems 💎")
        return
    text = ""
    for i, (title, url) in enumerate(favs):
        text += f"{i+1}. <a href='{url}'>{title}</a>\n"
    await message.reply(f"⭐️ Here are your faves, music freak 🎵:\n{text}", parse_mode='HTML', disable_web_page_preview=False)

@dp.message(Command("addfavorite"))
async def addfavorite_handler(message: types.Message, command: CommandObject):
    try:
        parts = command.args.strip().split(maxsplit=1)
        title, url = parts
        db_add_favorite(message.from_user.id, title, url)
        await message.reply(f"💾 Boom! <b>{title}</b> saved to your faves 🔥 You got taste 😎", parse_mode='HTML')
    except Exception:
        await message.reply("❓ Usage: /addfavorite <title> <url> — Don’t make me guess 😂")

@dp.message(Command("history"))
async def history_handler(message: types.Message):
    hist = db_list_history(message.from_user.id)
    if not hist:
        await message.reply("No history found 😢 Time to /play some music!")
        return
    text = ""
    for i, (title, url) in enumerate(hist):
        text += f"{i+1}. <a href='{url}'>{title}</a>\n"
    await message.reply(f"🕓 Your last 10 beats, bro 🎶:\n{text}", parse_mode='HTML', disable_web_page_preview=False)

@dp.message(Command("lyrics"))
async def lyrics_handler(message: types.Message, command: CommandObject):
    query = command.args
    if not query:
        await message.reply("❓ Usage: /lyrics <song>")
        return
    msg = await message.reply(f"🔍 Searching lyrics for <b>{query}</b>... Let's see what we got 🎙️📖", parse_mode='HTML')
    try:
        song = genius.search_song(query)
        if not song:
            await msg.edit_text("❌ Damn! Couldn’t find the lyrics 😩 Try tweaking the name.")
            return
        lyrics = song.lyrics
        if len(lyrics) > 4096:
            lyrics = lyrics[:4090] + "..."
        await msg.edit_text(f"🔥 Here you go, poetic soul:\n\n<b>{song.title} - {song.artist}</b>\n\n{lyrics}", parse_mode='HTML')
    except Exception:
        await msg.edit_text("❌ Damn! Couldn’t find the lyrics 😩 Try tweaking the name.")

@dp.inline_query()
async def inline_query_handler(inline_query: types.InlineQuery):
    query = inline_query.query.strip()
    if not query:
        await inline_query.answer([], cache_time=1)
        return
    filename, title, url, duration, thumb = await download_audio(query)
    if not filename:
        await inline_query.answer([], cache_time=1)
        return
    results = [
        InlineQueryResultAudio(
            id='1',
            audio_url=url,
            title=title,
            performer="YouTube",
            caption=f"🎧 Sending that beat from YouTube 🔥 Enjoy the ride, mate!",
            duration=duration
        )
    ]
    await inline_query.answer(results, cache_time=10, is_personal=True)
    try:
        os.remove(filename)
    except Exception:
        pass

@dp.message(Command("help"))
async def help_handler(message: types.Message):
    await message.reply(
        "📖 Yo homie! Here's the full menu. Pick your jam, run the bot, rule the vibe 🔥🎵 Type /play <song> and let’s go!"
    )

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))

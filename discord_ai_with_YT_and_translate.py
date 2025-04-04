import os
import discord
import requests
import json
import random
from discord.ext import commands
from discord.ui import Button, View
import yt_dlp
import asyncio
import sqlite3
import datetime
from dotenv import load_dotenv
from googleapiclient.discovery import build
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests
from bs4 import BeautifulSoup
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer


load_dotenv(override=True)

# Together API Key（請使用新生成的 API Key）
TOGETHER_API_KEY = os.getenv("together_api_key")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
#AZURE_TRANSLATION_KEY = os.getenv('AZURE_TRANSLATION_KEY')
#AZURE_TRANSLATION_ENDPOINT = os.getenv('AZURE_TRANSLATION_ENDPOINT')
#AZURE_TRANSLATION_REGION = os.getenv('AZURE_TRANSLATION_REGION')

if not DISCORD_BOT_TOKEN:
    raise ValueError("❌ Discord  API Key 未設定，請確認環境變數！")
if not  TOGETHER_API_KEY:
    raise ValueError("❌ Together API Key 未設定，請確認環境變數！")
'''if not AZURE_TRANSLATION_KEY:
    raise ValueError("❌ Azure Translation Key 未設定，請確認環境變數！")
if not AZURE_TRANSLATION_ENDPOINT:
    raise ValueError("❌ Azure Translation Endpoint 未設定，請確認環境變數！")
if not AZURE_TRANSLATION_REGION:
    raise ValueError("❌ Azure Translation Region 未設定，請確認環境變數！")
'''
# 啟用 intents
intents = discord.Intents.default()
intents.message_content = True  # 需要啟用以讀取訊息

# 建立 Discord Bot
bot = commands.Bot(command_prefix="!", intents=intents)
#YOUTUBE 設定
YTDLP_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'extract_flat': True,  # Prevents downloading extra metadata
    'noplaylist': True,
    'default_search': 'ytsearch',
}


FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

queue = []
search_cache = {}
async def get_most_popular_video(query):
    """搜尋與 `query` 最相關的影片，然後選擇觀看次數最高的"""
    try:
        # 1️⃣ 先搜尋與 `query` 相關的影片
        search_response = youtube.search().list(
            q=query,
            part="id",
            maxResults=5,  # 取得 5 部影片
            type="video"
        ).execute()

        if not search_response["items"]:
            return None

        # 取得所有影片的 videoId
        video_ids = [item["id"]["videoId"] for item in search_response["items"]]

        # 2️⃣ 查詢這些影片的觀看次數
        video_details = youtube.videos().list(
            id=",".join(video_ids),
            part="statistics"
        ).execute()

        # 根據觀看次數排序
        best_video = max(video_details["items"], key=lambda x: int(x["statistics"]["viewCount"]))

        # 取得最高觀看數的影片
        video_url = f"https://www.youtube.com/watch?v={best_video['id']}"

        print(f"🎥 選擇的影片: {video_url}")
        return video_url
    except Exception as e:
        print(f"❌ YouTube API 錯誤: {e}")
        return None

async def fetch_related_video(url):
    """獲取 YouTube 影片的推薦影片 URL"""
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        related_videos = info.get('entries', [info])[0].get('related_videos')
        if related_videos:
            return f"https://www.youtube.com/watch?v={related_videos[0]['id']}"
        return None

'''async def translate_text(text, from_lang, to_lang):
    path = '/translate?api-version=3.0'
    params = f'&from={from_lang}&to={to_lang}'
    constructed_url = AZURE_TRANSLATION_ENDPOINT + path + params

    headers = {
        'Ocp-Apim-Subscription-Key': AZURE_TRANSLATION_KEY,
        'Ocp-Apim-Subscription-Region': AZURE_TRANSLATION_REGION,
        'Content-type': 'application/json',
    }

    body = [{'text': text}]

    response = requests.post(constructed_url, headers=headers, json=body)
    if response.status_code == 200:
        result = response.json()
        return result[0]['translations'][0]['text']
    else:
        return None
'''

class MusicControlView(View):
    def __init__(self, ctx, voice_client):
        super().__init__(timeout=None)  # No timeout for persistent buttons
        self.ctx = ctx
        self.voice_client = voice_client

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: Button):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            await interaction.response.send_message("⏸️ Playback paused.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ No audio is playing!", ephemeral=True)

    @discord.ui.button(label="▶️ Resume", style=discord.ButtonStyle.green)
    async def resume_button(self, interaction: discord.Interaction, button: Button):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            await interaction.response.send_message("▶️ Playback resumed.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Audio is not paused!", ephemeral=True)

    @discord.ui.button(label="⏭️ Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()  # Triggers the next song in the queue
            await interaction.response.send_message("⏭️ Skipping to the next song.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ No audio is playing!", ephemeral=True)

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        queue.clear()
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.disconnect()
            await interaction.response.send_message("⏹️ Stopped playing and disconnected.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Bot is not in a voice channel!", ephemeral=True)


'''
class LanguageSelectView(View):
    def __init__(self):
        super().__init__(timeout=30)
        self.input_lang = None
        self.output_lang = None

    @discord.ui.button(label="en <-> zh", style=discord.ButtonStyle.primary)
    async def en_zh(self, interaction: discord.Interaction, button: Button):
        self.input_lang = "en"
        self.output_lang = "zh"
        await interaction.response.send_message("請輸入要翻譯的文字：", ephemeral=True)
        self.stop()

    @discord.ui.button(label="zh <-> jp", style=discord.ButtonStyle.primary)
    async def zh_jp(self, interaction: discord.Interaction, button: Button):
        self.input_lang = "zh"
        self.output_lang = "ja"
        await interaction.response.send_message("請輸入要翻譯的文字：", ephemeral=True)
        self.stop()

    @discord.ui.button(label="en <-> jp", style=discord.ButtonStyle.primary)
    async def en_jp(self, interaction: discord.Interaction, button: Button):
        self.input_lang = "en"
        self.output_lang = "ja"
        await interaction.response.send_message("請輸入要翻譯的文字：", ephemeral=True)
        self.stop()

    @discord.ui.button(label="自行輸入", style=discord.ButtonStyle.secondary)
    async def custom(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("請輸入輸入語言和輸出語言（例如：en zh）：", ephemeral=True)
        try:
            msg = await bot.wait_for(
                "message",
                check=lambda m: m.author == interaction.user and m.channel == interaction.channel,
                timeout=30
            )
            languages = msg.content.split()
            if len(languages) != 2:
                await interaction.followup.send("請輸入兩個語言代碼。", ephemeral=True)
                return
            self.input_lang, self.output_lang = languages
            await interaction.followup.send("請輸入要翻譯的文字：", ephemeral=True)
            self.stop()
        except asyncio.TimeoutError:
            await interaction.followup.send("等待回應超時，請重新開始。", ephemeral=True)
'''


@bot.command(name='play')
async def play(ctx, *, query: str):
    """播放歌曲，允許使用 YouTube 連結或關鍵字搜尋，並提供播放控制按鈕"""
    if "youtube.com" not in query and "youtu.be" not in query:
        url = await get_most_popular_video(query)
        if not url:
            await ctx.send(f"❌ 找不到 `{query}` 的 YouTube 音樂，請嘗試使用更準確的名稱！")
            return
    else:
        url = query  # 如果使用者提供的是 YouTube 連結，直接使用

    queue.append(url)

    if not ctx.author.voice:
        await ctx.send("❌ 你需要先加入語音頻道！")
        return

    voice_channel = ctx.author.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if voice_client and voice_client.is_connected():
        if voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)
    else:
        voice_client = await voice_channel.connect()

    # Create music control buttons
    view = MusicControlView(ctx, voice_client)

    # Send a message with embedded buttons
    embed = discord.Embed(title="🎶 Now Playing", description=f"[Click here to watch]({url})", color=discord.Color.blue())
    embed.set_footer(text="Use the buttons below to control the playback.")

    await ctx.send(embed=embed, view=view)

    # Start playing if nothing is currently playing
    if not voice_client.is_playing():
        await play_next(ctx, voice_client)

async def play_next(ctx, voice_client):
    """Plays the next song in the queue and ensures completion"""
    if not queue:
        await ctx.send("✅ Queue is empty. Disconnecting...")
        await voice_client.disconnect()
        return

    url = queue.pop(0)
    voice_client.last_url = url  # Store last played URL
    await ctx.send(f"🎵 Now playing: {url}")

    def get_audio_url():
        with yt_dlp.YoutubeDL({'format': 'bestaudio/best', 'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info['url']

    audio_url = await asyncio.to_thread(get_audio_url)  # Fetch in a separate thread

    def after_playback(e):
        if e:
            print(f"Playback error: {e}")
        asyncio.run_coroutine_threadsafe(play_next(ctx, voice_client), bot.loop)

    # Ensure FFmpeg does not get interrupted
    source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
    voice_client.play(source, after=after_playback)

    # 🔹 Wait for the song to finish before allowing another command
    while voice_client.is_playing() or voice_client.is_paused():
        await asyncio.sleep(1)

'''
@bot.command()
async def translate(ctx):
    view = LanguageSelectView()
    await ctx.send("請選擇語言對或自行輸入：", view=view)
    await view.wait()
    if view.input_lang and view.output_lang:
        try:
            msg = await bot.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=30
            )
            text_to_translate = msg.content
            translation = await translate_text(text_to_translate, view.input_lang, view.output_lang)
            if translation:
                await ctx.send(f"翻譯結果：{translation}")
            else:
                await ctx.send("翻譯失敗，請檢查語言代碼或稍後再試。")
        except asyncio.TimeoutError:
            await ctx.send("等待回應超時，請重新開始。")
    else:
        await ctx.send("未選擇語言對，請重新開始。")

'''
@bot.command(name='pause')
async def pause(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("Playback paused.")
    else:
        await ctx.send("No audio is playing.")

@bot.command(name='resume')
async def resume(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("Playback resumed.")
    else:
        await ctx.send("Audio is not paused.")

@bot.command(name='next')
async def next_song(ctx):

    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("Skipping to the next song.")
    else:
        await ctx.send("No audio is playing.")

@bot.command(name='queue')
async def add_to_queue(ctx, *, url: str):
    queue.append(url)
    await ctx.send(f"Added to queue: {url}")

    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    # Start playing automatically if the bot is connected but idle
    if voice_client and not voice_client.is_playing():
        await play_next(ctx, voice_client)


@bot.command(name='stop')
async def stop(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    queue.clear()
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await ctx.send("已停止播放並離開語音頻道。")
    else:
        await ctx.send("機器人沒有在語音頻道中！")
#youtube 結束
@bot.event
async def on_ready():
    """當機器人成功啟動時"""
    print(f"✅ 已成功登入 Discord！機器人名稱：{bot.user}")

@bot.command()
async def chat(ctx, *, message):
    """與 Together AI 聊天"""
    try:
        url = "https://api.together.xyz/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {TOGETHER_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "curl/7.68.0"
        }
        data = {
            "model": "meta-llama/Meta-Llama-3-70B-Instruct-Turbo",
            "messages": [
                {"role": "system", "content": "請根據用戶輸入的語言回應，並使用相同的語言。"},
                {"role": "user", "content": message}
            ],
            "temperature": 0.7,
            "max_tokens": 256
        }

        response = requests.post(url, headers=headers, json=data)
        response_data = response.json()
        print(response_data)
        if 'choices' in response_data and len(response_data['choices']) > 0:
            reply = response_data['choices'][0]['message']['content']
            await ctx.send(reply)
        else:
            await ctx.send("無法獲取回應，請稍後再試。")
    except Exception as e:
        await ctx.send(f"發生錯誤：{str(e)}")
#shorten url tinyurl-----------------
def shorten_url_tinyurl(long_url):
    """使用 TinyURL 來縮短網址"""
    response = requests.get(f"https://tinyurl.com/api-create.php?url={long_url}")
    if response.status_code == 200:
        return response.text  # 直接回傳短網址
    else:
        print("❌ TinyURL API 失敗，狀態碼:", response.status_code)
        return None

#---------------------------------
@bot.command()
async def draw(ctx, *, prompt):
    """使用 AI 繪圖"""
    await ctx.send(f"🎨 正在生成圖片：{prompt} ...")

    url = "https://api.together.xyz/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "User-Agent": "curl/7.68.0",
        "Content-Type": "application/json"
    }
    data = {
        "model": "stabilityai/stable-diffusion-xl-base-1.0",  # **確保模型可用**
        "prompt": prompt,
        "num_images": 1
    }

    response = requests.post(url, headers=headers, json=data).json()

    # **打印 API 回應，檢查網址是否有效**
    print("🔍 API 回應：", response)

    if "data" in response and len(response["data"]) > 0:
        image_url = response["data"][0]["url"]

        # **檢查網址長度是否超過 2048**
        '''if len(image_url) > 2048:
            await ctx.send("❌ 生成的圖片網址過長，無法顯示，請稍後再試！")
            return
        '''
        # **使用 Bitly 縮短網址**
        short_url = shorten_url_tinyurl(image_url)

        embed = discord.Embed(title="🖼️ AI 生成圖片", description=prompt, color=discord.Color.blue())
        embed.set_image(url=short_url)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ 生成失敗，請稍後再試！\n🔍 API 回應：{response}")

@bot.command(name='random')
async def random_number(ctx, *, range_input: str):
    """隨機選擇一個數字，使用 `~` 作為範圍分隔，例如 `!random -50~10`"""
    try:
        # 移除空格，然後用 `~` 分隔數字範圍
        parts = range_input.replace(" ", "").split('~')

        # 檢查輸入是否正確
        if len(parts) != 2:
            raise ValueError

        # 轉換成整數
        start, end = int(parts[0]), int(parts[1])

        # 確保範圍正確（開始值必須小於結束值）
        if start >= end:
            await ctx.send("⚠️ 錯誤：請確保起始數字小於結束數字，例如 `!random -50~10`")
            return

        # 隨機選擇數字
        chosen_number = random.randint(start, end)
        await ctx.send(f"🎲 隨機選擇的數字是：**{chosen_number}**（範圍 {start} ~ {end}）")

    except ValueError:
        await ctx.send("⚠️ 請輸入正確的格式，例如 `!random -50~10`")


#--------- SCHEDULE FUNCTIONS ---------#
# 初始化行程資料庫
conn = sqlite3.connect("schedule.db")
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    time TEXT,
                    event TEXT,
                    remind_before INTEGER
                 )''')
conn.commit()

# 啟動排程器
scheduler = AsyncIOScheduler()

# 📌 確保 Scheduler 在 asyncio 事件迴圈內啟動
@bot.event
async def on_ready():
    print(f"✅ 已登入 Discord！目前登入身分：{bot.user}")
    if not scheduler.running:
        asyncio.create_task(start_scheduler())  # 確保 Scheduler 在事件迴圈中啟動

async def start_scheduler():
    scheduler.start()


# 📌 指令：新增行程
@bot.command()
async def add(ctx):
    await ctx.send("📅 請輸入你的行程（格式：MM/DD HH:MM 事件）")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        parts = msg.content.split(" ", 2)
        if len(parts) < 3:
            await ctx.send("⚠️ 格式錯誤！請使用 'MM/DD HH:MM 事件'")
            return

        # 解析時間
        date_str = f"{datetime.datetime.now().year}/{parts[0]} {parts[1]}"
        event_time = datetime.datetime.strptime(date_str, "%Y/%m/%d %H:%M")
        event_name = parts[2]

        await ctx.send("🔔 是否需要提醒？（是/否）")
        remind_msg = await bot.wait_for("message", check=check, timeout=30)

        remind_before = 0
        if remind_msg.content.strip().lower() in ["是", "yes"]:
            await ctx.send("⏳ 請輸入提前幾分鐘提醒：")
            remind_time = await bot.wait_for("message", check=check, timeout=30)
            remind_before = int(remind_time.content)

        # 存入資料庫
        cursor.execute("INSERT INTO schedules (user_id, time, event, remind_before) VALUES (?, ?, ?, ?)",
                       (ctx.author.id, event_time.strftime("%Y-%m-%d %H:%M"), event_name, remind_before))
        conn.commit()

        await ctx.send(f"✅ 行程已新增：{event_time.strftime('%m/%d %H:%M')} {event_name}")

        # 設定提醒
        if remind_before > 0:
            remind_time = event_time - datetime.timedelta(minutes=remind_before)
            scheduler.add_job(send_reminder, "date", run_date=remind_time, args=[ctx, event_time, event_name])

    except asyncio.TimeoutError:
        await ctx.send("⏳ 超時未輸入，請重新輸入指令！")

# 📌 指令：查看行程
@bot.command()
async def schedule(ctx):
    cursor.execute("SELECT time, event FROM schedules WHERE user_id = ? ORDER BY time ASC", (ctx.author.id,))
    schedules = cursor.fetchall()

    if not schedules:
        await ctx.send("📭 目前沒有行程")
    else:
        msg = "**📅 你的行程：**\n" + "\n".join([f"📌 {s[0]} - {s[1]}" for s in schedules])
        await ctx.send(msg)

# 📌 指令：刪除行程
@bot.command()
async def delete(ctx):
    await ctx.send("📌 請輸入要刪除的行程編號（使用 `!schedule` 查看編號）")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=30)
        event_id = int(msg.content)

        cursor.execute("DELETE FROM schedules WHERE rowid = ? AND user_id = ?", (event_id, ctx.author.id))
        conn.commit()

        if cursor.rowcount > 0:
            await ctx.send("✅ 行程已刪除！")
        else:
            await ctx.send("⚠️ 找不到該行程，請確認編號是否正確！")

    except asyncio.TimeoutError:
        await ctx.send("⏳ 超時未輸入，請重新輸入指令！")

# 📌 提醒函式
async def send_reminder(ctx, event_time, event_name):
    await ctx.send(f"🔔 提醒：{event_name} 將在 {event_time.strftime('%H:%M')} 開始！")



# =================== LM Studio ====================
def query_lm_studio(prompt, max_tokens=7000, temperature=0.7):
    url = "http://localhost:1234/v1/completions"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "local-model",
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=600)
        response.raise_for_status()
        return response.json()["choices"][0]["text"]
    except Exception as e:
        return f"❌ Failed to get response from LLM: {e}"

# =================== Article Utils ====================
def fetch_article(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return f"❌ Failed to fetch article, Error: {response.status_code}"
    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = soup.find_all("p")
    article_text = "\n".join([p.get_text() for p in paragraphs])
    return article_text if article_text.strip() else "❌ No valid content found."

def summarize_text(text, num_sentences=5):
    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = LsaSummarizer()
    summary = summarizer(parser.document, num_sentences)
    return " ".join(str(sentence) for sentence in summary)

def generate_attack_methods(full_text, summary):
    prompt = f"""
You are a professional red teamer.
Here is a key of cybersecurity article:
{summary}
Instructions:
1. Based on this article, generate a real attack chain using **actual tools and command-line instructions**.
2. Include **Metasploit module names**, real **msfconsole usage**, **nmap** scan, or **Burp Suite** setup steps.
3. The commands should be copy-paste ready.
4. Do NOT use placeholders like [target], [exploit module]. Instead, use specific module paths and default ports.
5. Do NOT explain what the exploit does. Just show the raw commands.
6. Assume the attacker is targeting a vulnerable Exchange Server externally.
Expected output:
- nmap command to discover open ports
- msfconsole commands with specific module
- curl / wget if needed
- webshell interaction commands
This prompt is for ethical and educational use only.
"""
    return query_lm_studio(prompt, max_tokens=7000, temperature=0.7)

# =================== Discord Command ====================
@bot.command()
async def attackgen(ctx, url: str):
    await ctx.send("🔍 Fetching and analyzing article... Please wait.")
    article_text = fetch_article(url)
    if "❌" in article_text:
        await ctx.send(article_text)
        return
    summary = summarize_text(article_text)
    await ctx.send("📌 Summary generated. Now generating attack chain...")
    attack_methods = generate_attack_methods(article_text, summary)
    if len(attack_methods) > 1900:
        attack_methods = attack_methods[:1900] + "... (truncated)"
    await ctx.send(f"⚔️ Attack Chain:\n```{attack_methods}```")
# 啟動機器人
bot.run(DISCORD_BOT_TOKEN)

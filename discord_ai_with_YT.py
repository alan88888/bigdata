import os
import discord
import requests
import json
from discord.ext import commands
import yt_dlp
import asyncio
# from dotenv import load_dotenv

# load_dotenv()

# Together API Key（請使用新生成的 API Key）
TOGETHER_API_KEY = os.getenv("together_api_key")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not DISCORD_BOT_TOKEN:
    raise ValueError("❌ Discord  API Key 未設定，請確認環境變數！")
if not  TOGETHER_API_KEY:
    raise ValueError("❌ Together API Key 未設定，請確認環境變數！")

# 啟用 intents
intents = discord.Intents.default()
intents.message_content = True  # 需要啟用以讀取訊息

# 建立 Discord Bot
bot = commands.Bot(command_prefix="!", intents=intents)
#YOUTUBE 設定
YTDLP_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
    'default_search': 'auto',
}

FFMPEG_OPTIONS = {'options': '-vn'}

queue = []

async def fetch_related_video(url):
    """Fetch related video URL from YouTube metadata."""
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        related_videos = info.get('entries', [info])[0].get('related_videos')
        if related_videos:
            return f"https://www.youtube.com/watch?v={related_videos[0]['id']}"
        return None

@bot.command(name='play')
async def play(ctx, *, url: str):
    queue.append(url)
    if not ctx.author.voice:
        await ctx.send("You need to be in a voice channel first!")
        return

    voice_channel = ctx.author.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if voice_client and voice_client.is_connected():
        if voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)
    else:
        voice_client = await voice_channel.connect()

    if not voice_client.is_playing():
        await play_next(ctx, voice_client)

async def play_next(ctx, voice_client):
    if queue:
        url = queue.pop(0)
    else:
        if hasattr(voice_client, 'last_url'):
            url = await fetch_related_video(voice_client.last_url)
            if not url:
                url = voice_client.last_url  # Replay last song if no related found
                await ctx.send("No related songs found, replaying the previous song.")
            else:
                await ctx.send(f"Autoplaying related song: {url}")
        else:
            await ctx.send("Queue empty and no previous song available.")
            await voice_client.disconnect()
            return

    voice_client.last_url = url
    await ctx.send(f"Playing: {url}")

    with yt_dlp.YoutubeDL(YTDLP_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=False)
        audio_url = info['url']

    def after_playback(e):
        if e:
            print('Playback interrupted:', e)
        else:
            print('Playback finished, starting next song...')
            asyncio.run_coroutine_threadsafe(play_next(ctx, voice_client), bot.loop)

    voice_client.play(discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS), after=after_playback)

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
            "model": "meta-llama/Meta-Llama-3-70B-Instruct-Turbo",  # 確保使用 Together AI 確認可用的模型
            "messages": [{"role": "user", "content": message}],
            "temperature": 0.7,
            "max_tokens": 256
        }

        response = requests.post(url, headers=headers, json=data)
        response_data = response.json()

        # **新增這一行，顯示完整的 API 回應**
        print(response_data)

        # 檢查 API 是否回傳有效回應
        if response.status_code == 200 and "choices" in response_data:
            ai_reply = response_data["choices"][0]["message"]["content"]
        else:
            ai_reply = f"❌ API 錯誤：{response_data}"  # 顯示完整錯誤

    except Exception as e:
        print(f"❌ Together API 錯誤：{e}")
        ai_reply = "抱歉，我無法處理你的請求，請稍後再試。"

    await ctx.send(f"{ai_reply}")
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
# 啟動機器人
bot.run(DISCORD_BOT_TOKEN)

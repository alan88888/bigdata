import os
import discord
import requests
import json
from discord.ext import commands
from discord.ui import Button, View
import yt_dlp
import asyncio
from dotenv import load_dotenv

load_dotenv()
TOGETHER_API_KEY = os.getenv("together_api_key")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
AZURE_TRANSLATION_KEY = os.getenv('AZURE_TRANSLATION_KEY')
AZURE_TRANSLATION_ENDPOINT = os.getenv('AZURE_TRANSLATION_ENDPOINT')
AZURE_TRANSLATION_REGION = os.getenv('AZURE_TRANSLATION_REGION')

if not DISCORD_BOT_TOKEN:
    raise ValueError("❌ Discord  API Key 未設定，請確認環境變數！")
if not  TOGETHER_API_KEY:
    raise ValueError("❌ Together API Key 未設定，請確認環境變數！")
if not AZURE_TRANSLATION_KEY:
    raise ValueError("❌ Azure Translation Key 未設定，請確認環境變數！")
if not AZURE_TRANSLATION_ENDPOINT:
    raise ValueError("❌ Azure Translation Endpoint 未設定，請確認環境變數！")
if not AZURE_TRANSLATION_REGION:
    raise ValueError("❌ Azure Translation Region 未設定，請確認環境變數！")

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
    
async def translate_text(text, from_lang, to_lang):
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
# 啟動機器人
bot.run(DISCORD_BOT_TOKEN)

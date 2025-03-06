import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('TOKEN')

if TOKEN is None:
    print("找不到 Token，請檢查.env檔案或環境變數設定！")
    exit()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)
YTDLP_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
}

FFMPEG_OPTIONS = {
    'options': '-vn',
}
@bot.command(name='play')
async def play(ctx, url: str):
    if not ctx.author.voice:
        await ctx.send("你需要先加入語音頻道！")
        return
    
    voice_channel = ctx.author.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_connected():
        await voice_client.move_to(voice_channel)
    else:
        voice_client = await voice_channel.connect()

    await ctx.send(f"正在播放: {url}")
    with yt_dlp.YoutubeDL(YTDLP_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=False)
        audio_url = info['url']
    voice_client.play(discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS), after=lambda e: print('播放結束', e))
    while voice_client.is_playing():
        await asyncio.sleep(1)
    
    await voice_client.disconnect()
@bot.command(name='stop')
async def stop(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await ctx.send("已停止播放並離開語音頻道。")
    else:
        await ctx.send("機器人沒有在語音頻道中！")

bot.run(TOKEN)

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

bot.run(TOKEN)

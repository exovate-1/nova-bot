import discord
import requests
import asyncio
import random
import json
import os
import nest_asyncio
import threading
from datetime import datetime, timezone
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from textblob import TextBlob  # For sentiment analysis
from difflib import SequenceMatcher  # For memory matching

# Initialize Flask app
app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    server = Thread(target=run)
    server.daemon = True
    server.start()

if __name__ == "__main__":
    keep_alive()

load_dotenv()
nest_asyncio.apply()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OWNER_ID = os.getenv("OWNER_ID")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MEMORY_FILE = "memory.json"
BLOCKED_CHANNELS_FILE = "blocked_channels.json"
MAX_MEMORY_ENTRIES = 500

intents = discord.Intents.all()
client = discord.Client(intents=intents)

bot_name = "Nova"
human_name = "Nova"

def load_blocked_channels():
    if not os.path.exists(BLOCKED_CHANNELS_FILE):
        return []
    try:
        with open(BLOCKED_CHANNELS_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_blocked_channels(channels):
    with open(BLOCKED_CHANNELS_FILE, "w") as f:
        json.dump(channels, f)

blocked_channels = load_blocked_channels()

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "w") as f:
            json.dump({"convos": []}, f)
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except:
        return {"convos": []}

def save_memory(mem):
    if len(mem["convos"]) > MAX_MEMORY_ENTRIES:
        mem["convos"] = mem["convos"][-MAX_MEMORY_ENTRIES:]
    with open(MEMORY_FILE, "w") as f:
        json.dump(mem, f, indent=4)

memory = load_memory()

def find_similar_past_response(message, threshold=0.8):
    best_match = None
    best_score = 0
    for convo in memory["convos"]:
        score = SequenceMatcher(None, convo["message"], message).ratio()
        if score > best_score and score >= threshold:
            best_match = convo["response"]
            best_score = score
    return best_match

def get_headers():
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

def create_payload(msg):
    return {
        "model": "deepseek/deepseek-chat",
        "messages": [{"role": "user", "content": msg}]
    }

async def generate_response(prompt):
    try:
        res = requests.post(API_URL, headers=get_headers(), json=create_payload(prompt))
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content'].strip()
        else:
            return "Not sure how to answer that."
    except:
        return "Error reaching my brain, try later."

async def simulate_typing(channel, msg):
    delay = max(len(msg.split()) * 2, 1.2)
    async with channel.typing():
        await asyncio.sleep(min(delay, 8))

def detect_mood(message):
    blob = TextBlob(message)
    polarity = blob.sentiment.polarity
    if polarity > 0.5:
        return "excited"
    elif polarity < -0.5:
        return "annoyed"
    elif polarity > 0:
        return "friendly"
    elif polarity < 0:
        return "chill"
    else:
        return "neutral"

@client.event
async def on_ready():
    print(f"{bot_name} online")
    await client.change_presence(status=discord.Status.online, activity=discord.Game(name="just chillin"))

@client.event
async def on_message(message):
    global blocked_channels
    if message.author == client.user:
        return

    msg = message.content.lower()
    user_id = str(message.author.id)
    channel_id = message.channel.id
    response = None

    if message.content.startswith("!arenblock") and str(message.author.id) == OWNER_ID:
        if channel_id not in blocked_channels:
            blocked_channels.append(channel_id)
            save_blocked_channels(blocked_channels)
            await message.channel.send("🔕 Nova is now blocked from this channel.")
        else:
            await message.channel.send("Already blocked.")
        return

    elif message.content.startswith("!arenunblock") and str(message.author.id) == OWNER_ID:
        if channel_id in blocked_channels:
            blocked_channels.remove(channel_id)
            save_blocked_channels(blocked_channels)
            await message.channel.send("✅ Nova is now unblocked from this channel.")
        else:
            await message.channel.send("Not blocked.")
        return

    if channel_id in blocked_channels:
        return

    if human_name.lower() in msg and bot_name.lower() not in msg:
        response = f"nah i'm {bot_name}"
        await message.channel.send(response)

    elif "join vc" in msg or "join call" in msg:
        if message.author.voice and message.author.voice.channel:
            try:
                await message.author.voice.channel.connect()
                response = "yo i'm in"
            except:
                response = "can't join rn"
        if response:
            await message.channel.send(response)

    elif "discord.gg" in msg:
        response = "bet, drop the link"
        await message.channel.send(response)

    else:
        if not hasattr(client, "focus_users"):
            client.focus_users = {}

        now = datetime.now(timezone.utc)
        last_focus_time = client.focus_users.get(user_id)
        is_recent_focus = last_focus_time and (now - last_focus_time).total_seconds() < 180
        mentioned_bot = bot_name.lower() in msg or human_name.lower() in msg or client.user.mentioned_in(message)

        if mentioned_bot or is_recent_focus or msg.startswith(bot_name.lower()) or msg.startswith(human_name.lower()):
            client.focus_users[user_id] = now

            mood = detect_mood(msg)
            cached_response = find_similar_past_response(msg)

            if cached_response:
                response = cached_response + " (from memory)"
            else:
                prompt = f"You're {bot_name}, a chill US dude. Talk like you're relaxed and real. Short replies, no emojis. Reply to: {msg}. Use a {mood} tone."
                response = await generate_response(prompt)

            if response:
                await simulate_typing(message.channel, response)
                await message.channel.send(response)

        elif random.random() < 0.1:
            response = await generate_response(f"React casually like a real dude. Respond to: {msg}")
            if response:
                await simulate_typing(message.channel, response)
                await message.channel.send(response)

    memory['convos'].append({
        "user": str(message.author),
        "message": msg,
        "response": response if response else "none",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    save_memory(memory)

@client.event
async def on_voice_state_update(member, before, after):
    if member == client.user:
        if after.channel:
            print(f"{human_name} joined VC: {after.channel.name}")
        elif before.channel:
            print(f"{human_name} left VC: {before.channel.name}")

threading.Thread(target=run).start()

async def start_bot():
    await client.start(DISCORD_BOT_TOKEN)

loop = asyncio.get_event_loop()
loop.create_task(start_bot())
loop.run_forever()

# ============================================================
#  Discord Bot — Weryfikacja | Tickety | Moderacja | Logi
#  Wymagania: pip install discord.py
#  Uruchomienie: python bot_share.py
# ============================================================

import io, re, json, asyncio, os, discord
from datetime import timedelta
from discord.ext import commands

# ============================================================
#  KONFIGURACJA — jedyne co musisz zmienić to TOKEN
# ============================================================

TOKEN               = MTQ5NzYyNzQzMjM3Nzc3ODE4Ng.GkkkVg.4c1tHeaHU0xvcUHDpEYaEJ8nCbaFg3H57Rnv2M   # <-- tylko to zmień
VERIFY_CHANNEL_ID   = 1497625826600947753
TICKET_CHANNEL_ID   = 1497698553714180227
ROLE_ID             = 1497637375117885560

# ============================================================

TICKET_LIMIT_PER_CATEGORY = 10
WARNINGS_FILE             = "warnings.json"
INVITE_PATTERN = re.compile(r"(discord\.gg|discord\.com/invite)/[a-zA-Z0-9\-]+", re.IGNORECASE)
LOG_CATEGORY_NAME = "Logs"
LOG_CHANNELS = {"messages":"messages","channels":"channels","joins":"joins","moderation":"moderation","roles":"roles"}

log_channel_ids  = {}
open_tickets     = {}
ticket_cat_count = {"nagroda": 0, "pomoc": 0, "inne": 0}

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.moderation = True
bot = commands.Bot(command_prefix="!", intents=intents)

TICKET_CATEGORIES = {
    "nagroda": ("🏆 Odebranie nagrody", "Opisz jaką nagrodę chcesz odebrać."),
    "pomoc":   ("🆘 Potrzebuje pomocy", "Opisz problem, a administracja wkrótce pomoże."),
    "inne":    ("💬 Inne",              "Opisz czego dotyczy ticket."),
}
TICKET_EMBED_TITLES = {"Ticket", "🎫 Otwórz ticket", "🎫 Ticket", "Tickets"}

def load_warnings():
    if os.path.exists(WARNINGS_FILE):
        with open(WARNINGS_FILE, "r") as f: return json.load(f)
    return {}

def save_warnings(data):
    with open(WARNINGS_FILE, "w") as f: json.dump(data, f, indent=2)

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="💠", style=discord.ButtonStyle.green, custom_id="verify_button")
    async def verify(self, interaction, button):
        role = interaction.guild.get_role(ROLE_ID)
        if role:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("Masz już rangi, Obczaj kanały!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nie znaleziono roli.", ephemeral=True)

def ticket_category_key(channel_name):
    for key in TICKET_CATEGORIES:
        if f"ticket-{key}-" in channel_name: return key
    return None

class CloseTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🔒 Zamknij ticket", style=discord.ButtonStyle.red, custom_id="close_ticket_button")
    async def close_ticket(self, interaction, button):
        channel = interaction.channel
        lines = []
        async for msg in channel.history(limit=300, oldest_first=True):
            if msg.author == bot.user and msg.embeds: continue
            lines.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author}: {msg.content or '[załącznik]'}")
        mod_ch = bot.get_channel(log_channel_ids.get("moderation"))
        if mod_ch and lines:
            file = discord.File(io.BytesIO("\n".join(lines).encode()), filename=f"transcript-{channel.name}.txt")
            embed = discord.Embed(title="📋 Ticket Zamknięty", description=f"Kanał: `{channel.name}`\nZamknął: {interaction.user.mention}", color=0x95a5a6)
            await mod_ch.send(embed=embed, file=file)
        key = ticket_category_key(channel.name)
        if key: ticket_cat_count[key] = max(0, ticket_cat_count.get(key, 0) - 1)
        uid = next((u for u, c in open_tickets.items() if c == channel.id), None)
        if uid: del open_tickets[uid]
        await interaction.response.send_message("🔒 Zamykanie ticketu...")
        await channel.delete(reason=f"Ticket zamknięty przez {interaction.user}")

class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Odebranie nagrody", value="nagroda", description="Odbierz nagrodę"),
            discord.SelectOption(label="Potrzebuje pomocy", value="pomoc",   description="Potrzebuję pomocy"),
            discord.SelectOption(label="Inne",              value="inne",    description="Inne"),
        ]
        super().__init__(placeholder="Wybierz kategorię...", options=options, custom_id="category_select")
    async def callback(self, interaction):
        guild, user, key = interaction.guild, interaction.user, self.values[0]
        category_name, category_desc = TICKET_CATEGORIES[key]
        if user.id in open_tickets:
            existing = guild.get_channel(open_tickets[user.id])
            if existing:
                await interaction.response.edit_message(content=f"❌ Masz już otwarty ticket: {existing.mention}", view=None); return
        if ticket_cat_count.get(key, 0) >= TICKET_LIMIT_PER_CATEGORY:
            await interaction.response.edit_message(content=f"❌ Za dużo otwartych ticketów (max {TICKET_LIMIT_PER_CATEGORY}).", view=None); return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        ch = await guild.create_text_channel(name=f"ticket-{key}-{user.name}", overwrites=overwrites)
        open_tickets[user.id] = ch.id
        ticket_cat_count[key] = ticket_cat_count.get(key, 0) + 1
        embed = discord.Embed(title=f"🎫 Ticket — {category_name}", description=f"Cześć {user.mention}! {category_desc}\n\nAby zamknąć ticket, kliknij przycisk poniżej.", color=0xeb346b)
        await ch.send(embed=embed, view=CloseTicketView())
        await interaction.response.edit_message(content=f"✅ Twój ticket: {ch.mention}", view=None)

class CategorySelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(CategorySelect())

class TicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="📨", style=discord.ButtonStyle.blurple, custom_id="open_ticket_button")
    async def open_ticket(self, interaction, button):
        await interaction.response.send_message("Co potrzebujesz?", view=CategorySelectView(), ephemeral=True)

async def get_log_channel(key):
    cid = log_channel_ids.get(key)
    return bot.get_channel(cid) if cid else None

async def send_log(key, embed):
    ch = await get_log_channel(key)
    if ch: await ch.send(embed=embed)

@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
async def cmd_slowmode(ctx, seconds: int):
    if not 0 <= seconds <= 21600: await ctx.send("❌ Wartość od 0 do 21600."); return
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send("✅ Slowmode **wyłączony**." if seconds == 0 else f"✅ Slowmode **{seconds}s**.")

@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def cmd_clear(ctx, amount: int):
    if not 1 <= amount <= 100: await ctx.send("❌ Wartość od 1 do 100."); return
    deleted = await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"✅ Usunięto **{len(deleted)-1}** wiadomości.")
    await asyncio.sleep(3); await msg.delete()

@bot.command(name="warn")
@commands.has_permissions(kick_members=True)
async def cmd_warn(ctx, user: discord.Member, *, reason: str):
    warnings = load_warnings(); uid = str(user.id)
    if uid not in warnings: warnings[uid] = []
    warnings[uid].append({"reason": reason, "moderator": str(ctx.author), "timestamp": discord.utils.utcnow().isoformat()})
    save_warnings(warnings); count = len(warnings[uid])
    await ctx.send(f"⚠️ {user.mention} dostał ostrzeżenie. Powód: **{reason}** | Łącznie: **{count}**")
    embed = discord.Embed(title="⚠️ Warn", color=0xf39c12)
    embed.add_field(name="Użytkownik", value=user.mention, inline=True)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
    embed.add_field(name="Powód", value=reason, inline=False)
    embed.timestamp = discord.utils.utcnow()
    await send_log("moderation", embed)

@bot.command(name="warnings")
@commands.has_permissions(kick_members=True)
async def cmd_warnings(ctx, user: discord.Member):
    warns = load_warnings().get(str(user.id), [])
    if not warns: await ctx.send(f"✅ {user.mention} nie ma ostrzeżeń."); return
    embed = discord.Embed(title=f"⚠️ Ostrzeżenia — {user}", color=0xf39c12)
    for i, w in enumerate(warns, 1):
        embed.add_field(name=f"#{i}", value=f"**Powód:** {w['reason']}\n**Przez:** {w['moderator']}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="clearwarn")
@commands.has_permissions(kick_members=True)
async def cmd_clearwarn(ctx, user: discord.Member):
    warnings = load_warnings(); uid = str(user.id)
    if uid in warnings: del warnings[uid]; save_warnings(warnings)
    await ctx.send(f"✅ Usunięto ostrzeżenia dla {user.mention}.")

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def cmd_mute(ctx, user: discord.Member, minutes: int, *, reason: str = "Brak powodu"):
    if not 1 <= minutes <= 40320: await ctx.send("❌ Czas od 1 do 40320 minut."); return
    await user.timeout(timedelta(minutes=minutes), reason=reason)
    await ctx.send(f"🔇 {user.mention} wyciszony na **{minutes} min**. Powód: **{reason}**")
    embed = discord.Embed(title="🔇 Mute", color=0x9b59b6)
    embed.add_field(name="Użytkownik", value=user.mention, inline=True)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
    embed.add_field(name="Czas", value=f"{minutes} min", inline=True)
    embed.add_field(name="Powód", value=reason, inline=False)
    embed.timestamp = discord.utils.utcnow()
    await send_log("moderation", embed)

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def cmd_kick(ctx, user: discord.Member, *, reason: str = "Brak powodu"):
    await user.kick(reason=reason)
    await ctx.send(f"👢 {user.mention} wyrzucony. Powód: **{reason}**")
    embed = discord.Embed(title="👢 Kick", color=0xe67e22)
    embed.add_field(name="Użytkownik", value=str(user), inline=True)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
    embed.add_field(name="Powód", value=reason, inline=False)
    embed.timestamp = discord.utils.utcnow()
    await send_log("moderation", embed)

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def cmd_ban(ctx, user: discord.Member, *, reason: str = "Brak powodu"):
    await user.ban(reason=reason, delete_message_days=1)
    await ctx.send(f"🔨 {user.mention} zbanowany. Powód: **{reason}**")
    embed = discord.Embed(title="🔨 Ban", color=0xe74c3c)
    embed.add_field(name="Użytkownik", value=str(user), inline=True)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
    embed.add_field(name="Powód", value=reason, inline=False)
    embed.timestamp = discord.utils.utcnow()
    await send_log("moderation", embed)

@bot.command(name="temprole")
@commands.has_permissions(manage_roles=True)
async def cmd_temprole(ctx, user: discord.Member, role: discord.Role, minutes: int):
    if not 1 <= minutes <= 10080: await ctx.send("❌ Czas od 1 do 10080 minut."); return
    await user.add_roles(role)
    await ctx.send(f"✅ {user.mention} dostał rolę **{role.name}** na **{minutes} min**.")
    async def remove_later():
        await asyncio.sleep(minutes * 60)
        try: await user.remove_roles(role)
        except: pass
    bot.loop.create_task(remove_later())

@bot.command(name="userinfo")
async def cmd_userinfo(ctx, user: discord.Member = None):
    user = user or ctx.author
    embed = discord.Embed(title=f"👤 {user}", color=user.color)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=str(user.id), inline=True)
    embed.add_field(name="Nickname", value=user.nick or "Brak", inline=True)
    embed.add_field(name="Konto od", value=discord.utils.format_dt(user.created_at, style="R"), inline=False)
    embed.add_field(name="Dołączył", value=discord.utils.format_dt(user.joined_at, style="R"), inline=False)
    roles = [r.mention for r in user.roles if r.name != "@everyone"]
    embed.add_field(name=f"Role ({len(roles)})", value=" ".join(roles) if roles else "Brak", inline=False)
    await ctx.send(embed=embed)

@cmd_slowmode.error
@cmd_clear.error
@cmd_warn.error
@cmd_warnings.error
@cmd_clearwarn.error
@cmd_mute.error
@cmd_kick.error
@cmd_ban.error
@cmd_temprole.error
async def cmd_error(ctx, error):
    if isinstance(error, commands.MissingPermissions): await ctx.send("❌ Brak uprawnień.")
    elif isinstance(error, commands.MissingRequiredArgument): await ctx.send(f"❌ Brakuje: `{error.param.name}`.")
    elif isinstance(error, commands.BadArgument): await ctx.send("❌ Nieprawidłowy argument.")
    else: await ctx.send("❌ Coś poszło nie tak.")

@bot.event
async def on_message(message):
    if message.author.bot: await bot.process_commands(message); return
    if not message.author.guild_permissions.manage_messages:
        if INVITE_PATTERN.search(message.content):
            await message.delete()
            msg = await message.channel.send(f"❌ {message.author.mention} Nie możesz wysyłać zaproszeń!")
            await asyncio.sleep(5); await msg.delete()
            embed = discord.Embed(title="🔗 Zaproszenie zablokowane", color=0xe74c3c)
            embed.add_field(name="Użytkownik", value=str(message.author), inline=True)
            embed.add_field(name="Kanał", value=message.channel.mention, inline=True)
            embed.timestamp = discord.utils.utcnow()
            await send_log("moderation", embed); return
    await bot.process_commands(message)

@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    embed = discord.Embed(title="🗑️ Wiadomość usunięta", color=0xe74c3c)
    embed.add_field(name="Autor", value=message.author.mention, inline=True)
    embed.add_field(name="Kanał", value=message.channel.mention, inline=True)
    embed.add_field(name="Treść", value=message.content or "*Brak*", inline=False)
    embed.timestamp = discord.utils.utcnow(); await send_log("messages", embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content: return
    embed = discord.Embed(title="✏️ Wiadomość edytowana", color=0xf39c12)
    embed.add_field(name="Autor", value=before.author.mention, inline=True)
    embed.add_field(name="Przed", value=before.content or "*Puste*", inline=False)
    embed.add_field(name="Po", value=after.content or "*Puste*", inline=False)
    embed.timestamp = discord.utils.utcnow(); await send_log("messages", embed)

@bot.event
async def on_member_join(member):
    embed = discord.Embed(title="👋 Dołączył", color=0x2ecc71)
    embed.add_field(name="Użytkownik", value=f"{member.mention} (`{member}`)", inline=False)
    embed.add_field(name="Konto od", value=discord.utils.format_dt(member.created_at, style="R"), inline=False)
    embed.set_thumbnail(url=member.display_avatar.url); embed.timestamp = discord.utils.utcnow()
    await send_log("joins", embed)

@bot.event
async def on_member_remove(member):
    embed = discord.Embed(title="🚪 Opuścił", color=0xe67e22)
    embed.add_field(name="Użytkownik", value=f"{member.mention} (`{member}`)", inline=False)
    embed.set_thumbnail(url=member.display_avatar.url); embed.timestamp = discord.utils.utcnow()
    await send_log("joins", embed)

@bot.event
async def on_member_ban(guild, user):
    embed = discord.Embed(title="🔨 Zbanowany", color=0xe74c3c)
    embed.add_field(name="Użytkownik", value=str(user), inline=False)
    embed.timestamp = discord.utils.utcnow(); await send_log("moderation", embed)

@bot.event
async def on_member_unban(guild, user):
    embed = discord.Embed(title="✅ Odbanowany", color=0x2ecc71)
    embed.add_field(name="Użytkownik", value=str(user), inline=False)
    embed.timestamp = discord.utils.utcnow(); await send_log("moderation", embed)

@bot.event
async def on_guild_channel_create(channel):
    embed = discord.Embed(title="➕ Kanał utworzony", color=0x2ecc71)
    embed.add_field(name="Nazwa", value=channel.name, inline=True)
    embed.timestamp = discord.utils.utcnow(); await send_log("channels", embed)

@bot.event
async def on_guild_channel_delete(channel):
    embed = discord.Embed(title="➖ Kanał usunięty", color=0xe74c3c)
    embed.add_field(name="Nazwa", value=channel.name, inline=True)
    embed.timestamp = discord.utils.utcnow(); await send_log("channels", embed)

@bot.event
async def on_guild_role_create(role):
    embed = discord.Embed(title="🎭 Rola utworzona", color=role.color)
    embed.add_field(name="Nazwa", value=role.name, inline=True)
    embed.timestamp = discord.utils.utcnow(); await send_log("roles", embed)

@bot.event
async def on_guild_role_delete(role):
    embed = discord.Embed(title="🗑️ Rola usunięta", color=0xe74c3c)
    embed.add_field(name="Nazwa", value=role.name, inline=True)
    embed.timestamp = discord.utils.utcnow(); await send_log("roles", embed)

async def setup_log_channels(guild):
    category = discord.utils.get(guild.categories, name=LOG_CATEGORY_NAME)
    if not category:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
        category = await guild.create_category(LOG_CATEGORY_NAME, overwrites=overwrites)
    for key, name in LOG_CHANNELS.items():
        existing = discord.utils.get(category.channels, name=name)
        if not existing: existing = await guild.create_text_channel(name, category=category)
        log_channel_ids[key] = existing.id

async def setup_verify_channel():
    channel = await bot.fetch_channel(VERIFY_CHANNEL_ID)
    async for message in channel.history(limit=10):
        if message.author == bot.user and message.embeds and message.embeds[0].title == "Weryfikacja":
            try: await message.delete()
            except: pass
            break
    embed = discord.Embed(title="Weryfikacja", description="Żeby widzieć wszystkie kanały kliknij przycisk.", color=0xeb346b)
    await channel.send(embed=embed, view=VerifyView())

async def setup_ticket_channel():
    channel = await bot.fetch_channel(TICKET_CHANNEL_ID)
    to_delete = []
    async for message in channel.history(limit=100):
        if message.author == bot.user and message.embeds and message.embeds[0].title in TICKET_EMBED_TITLES:
            to_delete.append(message)
    for msg in to_delete:
        try: await msg.delete()
        except: pass
    embed = discord.Embed(title="Ticket", description="Kliknij w przycisk i otwórz ticket.", color=0x5865F2)
    await channel.send(embed=embed, view=TicketView())

@bot.event
async def on_ready():
    print(f"Bot gotowy: {bot.user}")
    bot.add_view(VerifyView())
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())
    for guild in bot.guilds:
        await setup_log_channels(guild)
    await setup_verify_channel()
    await setup_ticket_channel()

bot.run(TOKEN)
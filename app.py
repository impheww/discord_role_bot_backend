import discord
from discord.ext import commands, tasks
import datetime
import pytz
import json
import requests
import asyncio
import os
from myserver import server_on

# ================= TOKEN =================
# Token อยู่ใน render
# ================= ID CHANNEL =================
OWNER_ID = 848068744303083551 # ID admin
# ================== CHANNEL ==================
LOG_CHANNEL_ID = 1470417750319960168 # ห้อง embed บอทซื้อยศอั่งเปา + ส่งข้อความลูปทุกๆ 1 ชั่วโมง
ANGPAO_CHANNEL_ID = 1470403835234357258 # ห้องคนส่งลิ้งก์อั่งเปามาให้ (ห้องรับตังค์)
SUCCESS_CHANNEL_ID = 1470997698004914197 # embed ซื้อยศสำเร็จ
# ================== ROLE ==================
ROLE_01 = 1082885961953853540 # บทบาท 1
ROLE_02 = 1082668970718527508 # บทบาท 2
ROLE_03 = 1082667309254054008 # บทบาท 3
ROLE_04 = 1082667313163157515 # บทบาท 4
# ================= INTENTS =================
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

cooldown = {}
pending_links = {}
# ================= BASE EMBED =================
def create_base_embed(title, member):
    embed = discord.Embed(
        title=title,
        color=0x00ff00
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed

# ================== READY ===================
@bot.event
async def on_ready():
    if not hourly_loop.is_running():
        hourly_loop.start()
    print("===================================")
    print(f"Bot Online: {bot.user}")
    print("===================================")
# =========== embed แจ้งเตือน/คนส่งลิ้งก์ ===========
def create_payment_embed(member, amount, role, link=None, status="SUCCESS"):
    color = 0x00ff00 if status == "SUCCESS" else 0xff0000

    embed = discord.Embed(
        title="🧧 มีการส่งลิงก์อั่งเปา ",
        color=color
    )
    embed.set_author(
        name=f"{member.display_name}",
        icon_url=member.display_avatar.url
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(name="👤 ผู้ใช้", value=member.mention, inline=True)
    embed.add_field(name="💰 ราคา", value=f"{amount} บาท", inline=True)
    embed.add_field(name="🎭 ยศ", value=role.mention, inline=True)

    if link:
        embed.add_field(name="🔗 ลิ้งก์อั่งเปา", value=link, inline=False)

    embed.add_field(
        name="📥 สถานะ",
        value="✅  รับเงินแล้ว และให้ยศแล้ว" if status == "SUCCESS" else "❌ รับเงินไม่ได้",
        inline=False
    )

    embed.set_footer(text="Payment System")

    return embed
# ============= backend price ================
PRICE_ROLE_MAP = {
    149.0: ROLE_01,
    79.0: ROLE_02,
    50.0: ROLE_03,
    30.0: ROLE_04
}
# ================ backend ===================
@bot.event
async def on_message(message):
    if message.author.bot and not message.webhook_id:
        return

    content = message.content
    print(f"📩 MESSAGE: {content}")

    if content.startswith("PAID:"):

        if message.author.id != OWNER_ID:
            return

        try:
            # TODO: เรียก API TrueWallet จริงตรงนี้

            # ตัวทดสอบ (อยากให้ error ก็เปิด)
            # raise Exception("หมดอายุ")

            pass

        except Exception as e:
            print(f"ERROR: {e}")
            embed = discord.Embed(
                title="`❌` ลิ้งก์อั่งเปานี้หมดอายุไปแล้ว",
                color=discord.Color.red()
            )
            await message.channel.send(embed=embed)
            return

        try:
            _, user_id, amount = content.split(":")
            user_id = int(user_id)
            amount = float(amount)

            print(f"👤 user_id: {user_id} | 💰 amount: {amount}")

        except ValueError:
            print("❌ format PAID ผิด")
            return

        guild = message.guild
        member = guild.get_member(user_id)

        if member is None:
            print("❌ ไม่เจอ user")
            return

        role_id = PRICE_ROLE_MAP.get(amount)

        if role_id is None:
            print("❌ ราคาไม่ตรง")
            return

        role = guild.get_role(role_id)

        if role in member.roles:
            await message.channel.send(
                content=f"📢 แจ้งเตือนถึง <@{OWNER_ID}>\n<@{user_id}> ❌ ซื้อยศ {role.mention} ซ้ำ",
            )
            await message.delete()
            return

        if role:
            link = pending_links.get(member.id)

            # ❌ ไม่มี link = ผิดปกติ
            if not link:
                print("❌ ไม่มี link แต่มี PAID")
                return

            # ❌ ลิ้งซ้ำ
            if link in used_links:
                await message.channel.send("❌ ลิ้งนี้ถูกใช้ไปแล้ว")
                return

            # ❌ ลิ้งไม่ตรง (กันมั่ว)
            if pending_links.get(member.id) != link:
                await message.channel.send("❌ ลิ้งไม่ตรง")
                return

            # ✅ ผ่าน → ค่อยให้ยศ
            await member.add_roles(role)

            # ✅ บันทึกลิ้ง
            used_links.add(link)
            save_links()
            # ===== success DM =====
            success_embed = discord.Embed(
                title="<a:2correct2:1478778308916412487>   ซื้อยศสำเร็จ!!",
                description=f"<a:tykub:1488140712158691348> **__คุณได้รับยศอัตโนมัติแล้ว!!__** <a:tykub:1488140712158691348>\n\n <:lovepink:1488101192633417798> <#1470997698004914197> ",
                color=discord.Color.green()
            )

            try:
                await member.send(embed=success_embed)
            except discord.Forbidden:
                pass

            print(f"✅ ให้ role {role.name} กับ {member}")

            # 👇 ดึง link
            link = pending_links.get(member.id)

            if not link:
                print("❌ ไม่มี link แต่มี PAID")
                return

            embed = create_payment_embed(member, amount, role, link=link)

            await message.channel.send(
                content=f"📢 แจ้งเตือนถึง <@{OWNER_ID}>",
                embed=embed
            )

            # 👇 ลบ link ออกจากระบบ
            pending_links.pop(member.id, None)

            # 👇 ลบข้อความ PAID
            await message.delete()

    await bot.process_commands(message)
# ================ กัน LINK ซ้ำ ===================
def load_links():

        if not os.path.exists("links.json"):
            return set()

        try:
            with open("links.json") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, ValueError):
                return set()

def save_links():
    with open("links.json", "w") as f:
        json.dump(list(used_links), f)

used_links = load_links()
# =========================
# ตรวจลิงก์ TrueWallet
# =========================
def is_valid_angpao(link: str) -> bool:
    link = link.strip().replace("<", "").replace(">", "")
    return "gift.truemoney.com" in link
# ==================================================
#  Model กรอกลิ้งก์ + หากกรอกลิ้งก์ถูกหรือผิด + แจ้งเตือนมีคนส่งลิ้งก์อั่งเปา
# ==================================================

class AngpaoModal(discord.ui.Modal, title="( กรุณากรอกลิงก์ซองอั่งเปา )"):

    def __init__(self, role_id):
        super().__init__()
        self.role_id = role_id

    link = discord.ui.TextInput(
        label="( 🧧 กรอกลิ้งก์ซองอั่งเปา )",
        placeholder="https://gift.truemoney.com/campaign/?v=xxxxxxxxxxxxxxxxxx",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:

        user_id = interaction.user.id
        now = datetime.datetime.now().timestamp()

        if user_id in cooldown and now - cooldown[user_id] < 10:
            await interaction.response.send_message("⏳ **กรุณารอ 10วิก่อนส่งใหม่**", ephemeral=True)
            return

        cooldown[user_id] = now

        link_value = self.link.value.strip().replace("<", "").replace(">", "")

        # ===== loading =====
        await interaction.response.defer(ephemeral=True)

        msg = await interaction.followup.send(
            content="<a:main_loading:1486624902739005450>   **กำลังตรวจสอบลิ้งก์** โปรดรอสักครู่...",
            ephemeral=True
        )

        # ===== ตรวจ format =====
        print("🔍 BOT VALID:", link_value, is_valid_angpao(link_value))
        if not is_valid_angpao(link_value):
            embed = discord.Embed(
                title="`❌` กรุณากรอกลิงค์ที่อยู่ซองอั่งเปาให้ถูกต้อง!!",
                color=discord.Color.red()
            )
            await msg.edit(content=None, embed=embed)
            return

        # ===== ลิ้งซ้ำ =====
        if link_value in used_links:
            embed = discord.Embed(
                title="`❌` ลิ้งนี้ถูกส่ง/ใช้ไปแล้ว",
                color=discord.Color.red()
            )
            await msg.edit(content=None, embed=embed)
            return

        pending_links[user_id] = link_value

        # ===== ยิง backend =====
        try:
            res = await asyncio.to_thread(
                requests.post,
                "https://discord-role-bot-backend.onrender.com/redeem",
                json={
                    "user_id": user_id,
                    "link": link_value
                },
                timeout=30
            )

            if res.status_code != 200:
                embed = discord.Embed(
                    title=f"`❌` ระบบมีปัญหาชั่วคราวโปรดลองใหม่อีกครั้งหรือแจ้งแอดมิน ({res.status_code})",
                    color=discord.Color.red()
                )
                await msg.edit(content=None, embed=embed)
                return

            # ===== ตรวจสถานะ =====
            try:
                data = res.json()
            except ValueError:
                embed = discord.Embed(
                    title="`❌` ระบบเกิดข้อผิดพลาด กรุณาแจ้งแอดมิน",
                    color=discord.Color.red()
                )
                await msg.edit(content=None, embed=embed)
                return

            success = data.get("success")

            if not success:
                error = data.get("error")

                if error == "invalid":
                    embed = discord.Embed(
                        title="`❌` กรุณากรอกลิงค์ที่อยู่ซองอั่งเปาให้ถูกต้อง!!",
                        color=discord.Color.red()
                    )
                    await msg.edit(content=None, embed=embed)
                    return

                if error == "used":
                    embed = discord.Embed(
                        title="`❌` ลิ้งก์นี้ถูกส่ง/ใช้ไปแล้ว",
                        color=discord.Color.red()
                    )
                    await msg.edit(content=None, embed=embed)
                    return

                if error == "processing":
                    embed = discord.Embed(
                        title="`⏳` มีคนกำลังใช้ลิ้งนี้อยู่",
                        color=discord.Color.red()
                    )
                    await msg.edit(content=None, embed=embed)
                    return

                await msg.edit(content=f"`❌` Error: {error}")
                return

        except requests.exceptions.RequestException as e:
            print("❌ BOT ERROR:", e)
            embed = discord.Embed(
                title=f"`❌` เชื่อมต่อไม่ได้: {e}",
                color=discord.Color.red()
            )
            await msg.edit(content=None, embed=embed)
            return

        except Exception as e:
            embed = discord.Embed(
                title="`❌` เกิดข้อผิดพลาดบางอย่าง",
                color=discord.Color.red()
            )
            await msg.edit(content=None, embed=embed)
            print("ERROR:", e)
            return

        finally:
            pending_links.pop(user_id, None)

        # ✅ SUCCESS
        amount = data.get("amount")

        role_id = PRICE_ROLE_MAP.get(amount)

        if not role_id:
            await msg.edit(content="`❌` ราคาไม่ตรงระบบ")
            return

        role = interaction.guild.get_role(role_id)

        member = interaction.user

        if role in member.roles:
            await msg.edit(content="`❌` คุณมียศนี้อยู่แล้ว")
            return

        # ✅ ให้ role ทันที
        await member.add_roles(role)

        # ✅ embed
        embed = discord.Embed(
            title="`✅` ซื้อยศสำเร็จ!!",
            description=f"ได้รับ {role.mention}\n\n```หากไม่ได้รับยศภายใน 10 วินาที กรุณาแจ้งแอดมิน```",
            color=discord.Color.green()
        )

        await msg.edit(content=None, embed=embed)

        # ✅ success channel
        channel = bot.get_channel(SUCCESS_CHANNEL_ID)
        if channel:
            await channel.send(embed=create_payment_embed(member, amount, role, link_value))
# ==================================================
#  Dropdown ช่องทางเติมเงิน (ตัวเลือก)
# ==================================================

class PaymentSelect(discord.ui.Select):

    def __init__(self):

        options = [
            discord.SelectOption(
                label="True Wallet",
                description="ซื้อด้วยซองอั่งเปา True Wallet",
                emoji=discord.PartialEmoji(name="angpao", id=1472134389763932350, animated=True)
            ),
            discord.SelectOption(
                label="PromptPay",
                description="ซื้อผ่านสแกน QR พร้อมเพย์ (ยังไม่เปิดใช้งาน!!)",
                emoji=discord.PartialEmoji(name="promtpay", id=1472134870368124998)
            ),
        ]

        super().__init__(
            placeholder="[ 🛒 เลือกช่องทางการเติมเงิน ]",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):

        choice = self.values[0]

        if choice == "True Wallet":
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="ꔛ เลือกยศและราคาที่ต้องการซื้อ ꔛ",
                    description="เลือกยศที่ต้องการซื้อผ่านซองอั่งเปา",
                    color=0x5C67ED
                ),
                view=RoleSelectView(),
                ephemeral=True
            )

        elif choice == "PromptPay":
            await interaction.response.send_message(
                "<a:wrong1:1477677468327350414> **ขออภัยช่องทาง __PromptPay__ ยังไม่มี**:pray:",
                ephemeral=True
            )


class PaymentView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PaymentSelect())

# ==================================================
#  RoleSelectView (เลือกราคาและบทบาท)
# ==================================================

ROLE_PRICES = {
    ROLE_01: 149.00,
    ROLE_02: 79.00,
    ROLE_03: 50.00,
    ROLE_04: 30.00
}

class RoleSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="𝐕𝐈𝐏・เห็นทุกห้อง + กลุ่มแรร์ๆ ꒰149บาท꒱",
                value=str(ROLE_01),
                description="ราคา 149.-",
                emoji=discord.PartialEmoji(name="star_1", id=1472134208993497202, animated=True)
            ),
            discord.SelectOption(
                label="𝐕𝐈𝐏・นานาชาติ ꒰79บาท꒱",
                value=str(ROLE_02),
                description="ราคา 79.-",
                emoji=discord.PartialEmoji(name="star_1", id=1472134208993497202, animated=True)
            ),
            discord.SelectOption(
                label="𝐕𝐈𝐏・𝑶𝒏𝒍𝒚𝒇𝒂𝒏𝒔 ꒰50บาท꒱",
                value=str(ROLE_03),
                description="ราคา 50.-",
                emoji=discord.PartialEmoji(name="star_1", id=1472134208993497202, animated=True)
            ),
            discord.SelectOption(
                label="𝐕𝐈𝐏・H/ANIME ꒰30บาท꒱",
                value=str(ROLE_04),
                description="ราคา 30.-",
                emoji=discord.PartialEmoji(name="star_1", id=1472134208993497202, animated=True)
            ),
        ]

        super().__init__(
            placeholder="[ 🛒 เลือกประเภทยศและราคา ]",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        price = ROLE_PRICES.get(role_id, 0)

        embed = discord.Embed(
            title="<a:angpao:1472134389763932350> เติมด้วยซองอั่งเปา",
            description="กรุณากดยืนยันการซื้อก่อนดำเนินการต่อ",
            color=0x5C67ED
        )

        embed.add_field(
            name="`💰` ราคายศที่ยืนยัน",
            value=f"```{price:.2f} THB```",
            inline=False
        )

        await interaction.response.send_message(
            embed=embed,
            view=ConfirmView(role_id),
            ephemeral=True
        )

# ==================================================
#  ConfirmView (ปุ่มยืนยัน/ยกเลิก)
# ==================================================

class RoleSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RoleSelect())

class ConfirmView(discord.ui.View):
    def __init__(self, role_id):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="ยืนยันการซื้อ", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(AngpaoModal(self.role_id))

    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="❌ ยกเลิกแล้ว", embed=None, view=None)

# ==================================================
#  PriceView (ปุ่มซื้อยศ/ปิดหน้าต่าง)
# ==================================================
class PriceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(
        label="ซื้อด้วยอั่งเปา",
        emoji=discord.PartialEmoji(name="truewallet_icon", id=1484455894283714701),
        style=discord.ButtonStyle.success
    )
    async def buy(self, interaction: discord.Interaction, _):
        embed = discord.Embed(
            title="ꔛ เลือกช่องทางเติมเงิน ꔛ",
            color=0x5C67ED
        )

        embed.set_image(
            url="https://images-ext-1.discordapp.net/external/xirWF0Vb4xRr7eX30asFDva_pZJAKltrQlBE3S8BOKo/https/img2.pic.in.th/pic/ds.png"
        )

        await interaction.response.send_message(
            embed=embed,
            view=PaymentView(),
            ephemeral=True
        )

    @discord.ui.button(
        label="ปิดหน้าต่าง",
        style=discord.ButtonStyle.secondary
    )
    async def close(self, interaction: discord.Interaction, _):

        embed = discord.Embed(
            title="ปิดหน้าต่างเรียบร้อยแล้ว",
            color=discord.Color.dark_grey()
        )

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=None
        )

# ==================================================
#  View เมนูหลัก (ปุ่มซื้อ + เลือกช่องทางเติมเงิน)
# ==================================================

class MainView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="ซื้อด้วยอั่งเปา",
        emoji=discord.PartialEmoji(name="truewallet_icon", id=1484455894283714701),
        style=discord.ButtonStyle.green
    )
    async def topup(self, interaction: discord.Interaction, _):

        embed = discord.Embed(
            title="ꔛ เลือกช่องทางเติมเงิน ꔛ",
            color=0x5C67ED
        )

        embed.set_image(
            url="https://images-ext-1.discordapp.net/external/xirWF0Vb4xRr7eX30asFDva_pZJAKltrQlBE3S8BOKo/https/img2.pic.in.th/pic/ds.png?format=webp&quality=lossless"
        )

        await interaction.response.send_message(
            embed=embed,
            view=PaymentView(),
            ephemeral=True
        )


    @discord.ui.button(
        label="ดูราคายศ",
        emoji="🛒",
        style=discord.ButtonStyle.primary
    )
    async def rank_info(self, interaction: discord.Interaction, _):

        embed = discord.Embed(
            title="⋆｡˚୨🛒・ราคายศทั้งหมด୧˚｡⋆",
            description=(
                "**‧˚꒷꒦︶︶꒷︶︶꒷︶+꒷︶꒷꒦︶︶꒷︶︶₊꒷**\n"
                "**🛒 ซื้อยศ 149.- จะได้รับ**\n"
                "<a:star1:1472134208993497202> <@&1082885961953853540>\n\n"
                
                "**‧˚꒷꒦︶︶꒷︶︶꒷︶+꒷︶꒷꒦︶︶꒷︶︶₊꒷**\n"
                "**🛒 ซื้อยศ 79.- จะได้รับ**\n"
                "<a:star1:1472134208993497202> <@&1082668970718527508>\n\n"
                
                "**‧˚꒷꒦︶︶꒷︶︶꒷︶+꒷︶꒷꒦︶︶꒷︶︶₊꒷**\n"
                "**🛒 ซื้อยศ 50.- จะได้รับ**\n"
                "<a:star1:1472134208993497202> <@&1082667309254054008>\n\n"
                
                "**‧˚꒷꒦︶︶꒷︶︶꒷︶+꒷︶꒷꒦︶︶꒷︶︶₊꒷**\n"
                "**🛒 ซื้อยศ 30.- จะได้รับ**\n"
                "<a:star1:1472134208993497202> <@&1082667313163157515>\n\n"
                
                "**‧˚꒷꒦︶︶꒷︶︶꒷︶+꒷︶꒷꒦︶︶꒷︶︶₊꒷**"
            ),
            color=0x5C67ED
        )

        embed.set_footer(
            text="🧧 ชำระผ่านซองอั่งเปา TrueWallet เท่านั้น"
        )

        await interaction.response.send_message(
            embed=embed,
            view=PriceView(),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions(roles=True)
        )

# ==================================================
#  embed ซื้อยศสำเร็จ (ส่วนของ ระบบอั่งเปา)
# ==================================================
@bot.command()
async def testembedsuccess(ctx):
    role = ctx.guild.get_role(ROLE_01)
    await send_purchase_success(ctx.author, role, bot.user)

async def send_purchase_success(member: discord.Member, role: discord.Role, giver):
    channel = bot.get_channel(SUCCESS_CHANNEL_ID)
    if channel is None:
        return

    # ====== เวลาไทย ======
    thai_tz = pytz.timezone("Asia/Bangkok")
    now = datetime.datetime.now(thai_tz).strftime("%d/%m/%Y %H:%M")

    embed = create_base_embed(
        "<a:correct3:1472134441248751788>  __ซื้อยศสำเร็จเรียบร้อยแล้ว!__  <a:bell_2:1472134346449354844>",
        member
    )

    embed.set_author(
        name=f"{member.display_name}",
        icon_url=member.display_avatar.url
    )

    embed.add_field(
        name=" ",
        value=f"`👤 ผู้ใช้ :` {member.mention}",
        inline=False
    )

    embed.add_field(
        name=" ",
        value=f"`🏅 ได้รับยศ :` {role.mention}",
        inline=False
    )

    if giver:
        embed.add_field(
            name=" ",
            value=f"`👮 ให้โดย :` {giver.mention}",
            inline=False
        )

    embed.add_field(
        name=" ",
        value=f" ",
        inline=False
    )

    embed.set_image(
        url="https://i.postimg.cc/3JkfNzdk/standard.gif"
    )

    guild = member.guild
    embed.set_footer(
        text=f"{guild.name} • {now}",
        icon_url=guild.icon.url if guild.icon else None
    )

    msg = await channel.send(embed=embed)
    await msg.add_reaction("✅")

# ==================================================
#  คำสั่งเปิดร้าน !shop
# ==================================================

@bot.command()
async def shop(ctx):

    if ctx.author.id != OWNER_ID:
        return
    # title อั่งเปา
    embed = discord.Embed(
        title=" <a:bowl_pink:1484474337061765122> 𝐀𝐔𝐓𝐎 𝐁𝐔𝐘 𝐑𝐎𝐋𝐄 <a:bowl_pink:1484474337061765122>  (ชำระผ่านทรูวอเล็ทเท่านั้น)",
        description="> **<a:angpao:1472134389763932350> ระบบซื้อยศอัตโนมัติ [24 ชั่วโมง] ✨** ",
        color=discord.Color.red()
    )
    # Gif บน embed อั่งเปา
    embed.set_image(
        url="https://i.pinimg.com/originals/b8/73/46/b873460b260b5cf96e3fe9a734799bb1.gif"
    )
    # ข้อความข้างล่าง embed อั่งเปา + ไอคอนเซิร์ฟซ้ายล่าง
    embed.set_footer(
        text="✅ ชำระผ่านซองอั่งเปายศเข้าตัวทันที 🔞",
        icon_url="https://media.discordapp.net/attachments/1478973402629935206/1483340274594877501/DOHEE_icon_png.png?ex=69be3048&is=69bcdec8&hm=c4674a41bb839e0f49652f7a00f2fcd78eaffb7ed418224d6e75e21a5e4a2368&=&format=webp&quality=lossless"
    )

    await ctx.send(embed=embed, view=MainView())
# ==================================================
#  ระบบให้ยศขึ้น embed ซื้อสำเร็จ
# ==================================================

@bot.event
async def on_member_update(before, after):
    # เช็ค role ที่เพิ่มเข้ามา
    added_roles = [r for r in after.roles if r not in before.roles]

    target_roles = [ROLE_01, ROLE_02, ROLE_03, ROLE_04]

    for role in added_roles:
        if role.id in target_roles:

            # หาใครเป็นคนให้ (จาก audit log)
            giver = None
            async for entry in after.guild.audit_logs(
                limit=5,
                action=discord.AuditLogAction.member_role_update
            ):
                if entry.target.id == after.id:
                    giver = entry.user
                    break

            # ถ้าไม่เจอ ให้เป็นคุณ (OWNER)
            if giver is None:
                giver = bot.get_user(OWNER_ID)

            await send_purchase_success(after, role, giver)

# ==================================================
#  ระบบส่งข้อความลูปทุกๆ 1 ชั่วโมง (ระบบอั่งเปา)
# ==================================================

@bot.command()
async def testloop(ctx):
    await ctx.send("ทดสอบระบบลูป...")
    await hourly_loop()

last_messages = []

@tasks.loop(minutes=1)
async def hourly_loop():

    now = datetime.datetime.now()

    # เช็คว่าเป็นต้นชั่วโมงไหม (นาที = 0)
    if now.minute != 0:
        return

    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel is None:
        return

    global last_messages

    # ลบข้อความเก่า
    for msg in last_messages:
        try:
            await msg.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass

    last_messages = []

    # ข้อความที่ 1
    msg1 = await channel.send("""
    # <a:star_1:1472134208993497202> วิธีการซื้อ <a:star_1:1472134208993497202>
    ### <a:correct2:1472846699495034981> ขั้นตอนที่ 1 : เข้า "__TrueWallet__" กดสร้างซองอั่งเปาใส่ราคาตามยศนั้นๆ <:truewallet:1472134849019248782>
    ### <a:correct2:1472846699495034981> ขั้นตอนที่ 2 : นำลิงก์ซองอั่งเปามาใส่ใน "__ซื้อด้วยอั่งเปา__" ได้เลยครับ! <a:angpao:1472134389763932350>
    > **<a:flower8:1472928911594885142> เช็คการซื้อยศสำเร็จได้ที่ <a:flower8:1472928911594885142>**
    ** <a:correct3:1472134441248751788> <#1470997698004914197> <a:vip1:1472132052026527754>**
    ||@everyone|| ||@everyone||
    """)

    # ข้อความที่ 2 (รูป GIF 1 รูป)
    gif1 = await channel.send("https://i.postimg.cc/7Lt8PrZM/rainbow-water-falling.gif")

    last_messages = [msg1, gif1]

# ================ TEST BOT ==================

@bot.command()
async def ping(ctx):
    await ctx.send("pong")

# ================= RUN =================

server_on()

bot.run(os.getenv('TOKEN'))

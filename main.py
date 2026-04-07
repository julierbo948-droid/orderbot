# main.py (Clone Bot function များ ဖြုတ်ပြီး)

import asyncio, os, re
from datetime import datetime, timedelta
from telegram import Update, Bot, User
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatMember

# env.py file မှ settings များကို import လုပ်ပါ
try:
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    ADMIN_ID = int(os.environ.get("ADMIN_ID"))
    MONGO_URL = os.environ.get("MONGO_URL")
    
    # --- Group ID ကို မူလ (Singular) ပုံစံသို့ ပြန်ပြောင်း ---
    ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID")) # 'S' မပါ၊ တစ်ခုတည်း
    
    if not all([BOT_TOKEN, ADMIN_ID, MONGO_URL, ADMIN_GROUP_ID]):
        print("Error: Environment variables များ (BOT_TOKEN, ADMIN_ID, MONGO_URL, ADMIN_GROUP_ID) မပြည့်စုံပါ။")
        exit()

except Exception as e:
    print(f"Error: Environment variables များ load လုပ်ရာတွင် အမှားဖြစ်နေပါသည်: {e}")
    exit()

# Database module ကို import လုပ်ပါ
try:
    import database as db
except ImportError:
    print("Error: database.py file ကို မတွေ့ပါ။")
    exit()
except Exception as e:
    print(f"Error: Database ချိတ်ဆက်မှု မအောင်မြင်ပါ: {e}")
    exit()

# history.py ကို import လုပ်ပါ
try:
    from history import clear_history_command
except ImportError:
    print("Error: history.py file ကို မတွေ့ပါ။")
    exit()


AUTHORIZED_USERS = db.load_authorized_users()
ADMIN_IDS = db.load_admin_ids(ADMIN_ID)

user_states = {}
DEFAULT_MAINTENANCE = {
    "orders": True,    
    "topups": True,    
    "general": True    
}

DEFAULT_PAYMENT_INFO = {
    "kpay_number": "09678786528",
    "kpay_name": "Ma May Phoo Wai",
    "kpay_image": None,  # Store file_id of KPay QR code image
    "wave_number": "09673585480",
    "wave_name": "Nine Nine",
    "wave_image": None   # Store file_id of Wave QR code image
}

# --- (အသစ်) Affiliate Default Setting ---
DEFAULT_AFFILIATE = {
    "percentage": 0.01  # 1%
}

DEFAULT_AUTO_DELETE = {
    "enabled": False, 
    "hours": 24    
}

# Global Settings Variable (Bot စတက်လျှင် DB မှ load လုပ်မည်)
g_settings = {}

# Pending topup process (In-memory)
pending_topups = {}

def load_global_settings():
    """
    Database မှ settings များကို g_settings global variable ထဲသို့ load လုပ်ပါ။
    """
    global g_settings
    # --- (ပြင်ဆင်ပြီး) Auto Delete Setting ကိုပါ load လုပ်ရန် ---
    g_settings = db.load_settings(DEFAULT_PAYMENT_INFO, DEFAULT_MAINTENANCE, DEFAULT_AFFILIATE, DEFAULT_AUTO_DELETE)
    print("✅ Global settings loaded from MongoDB.")
    
    if "affiliate" not in g_settings:
        g_settings["affiliate"] = DEFAULT_AFFILIATE
        db.update_setting("affiliate", DEFAULT_AFFILIATE)
    elif "percentage" not in g_settings["affiliate"]:
        g_settings["affiliate"]["percentage"] = DEFAULT_AFFILIATE["percentage"]
        db.update_setting("affiliate.percentage", DEFAULT_AFFILIATE["percentage"])

    if "auto_delete" not in g_settings:
        g_settings["auto_delete"] = DEFAULT_AUTO_DELETE
        db.update_setting("auto_delete", DEFAULT_AUTO_DELETE)


# --- Helper Functions ---

def is_user_authorized(user_id):
    """Check if user is authorized to use the bot (uses global set)"""
    return str(user_id) in AUTHORIZED_USERS or int(user_id) == ADMIN_ID

def is_owner(user_id):
    """Check if user is the owner"""
    return int(user_id) == ADMIN_ID

def is_admin(user_id):
    """Check if user is any admin (uses global list)"""
    return int(user_id) in ADMIN_IDS

def load_authorized_users():
    """Reload authorized users from DB into global set"""
    global AUTHORIZED_USERS
    AUTHORIZED_USERS = db.load_authorized_users()

def load_admin_ids_global():
    """Reload admin IDs from DB into global list"""
    global ADMIN_IDS
    ADMIN_IDS = db.load_admin_ids(ADMIN_ID)

async def is_bot_admin_in_group(bot, chat_id):
    """Check if bot is admin in the group"""
    try:
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(chat_id, me.id)
        is_admin = bot_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
        print(f"Bot admin check for group {chat_id}: {is_admin}, status: {bot_member.status}")
        return is_admin
    except Exception as e:
        print(f"Error checking bot admin status in group {chat_id}: {e}")
        return False

def simple_reply(message_text):
    """
    Simple auto-replies for common queries
    """
    message_lower = message_text.lower()

    # Greetings
    if any(word in message_lower for word in ["hello", "hi", "မင်္ဂလာပါ", "ဟယ်လို", "ဟိုင်း", "ကောင်းလား"]):
        return ("👋 မင်္ဂလာပါ!  𝙅𝘽 𝙈𝙇𝘽𝘽 𝘼𝙐𝙏𝙊 𝙏𝙊𝙋 𝙐𝙋 𝘽𝙊𝙏 မှ ကြိုဆိုပါတယ်!\n\n"
                "📱 Bot commands များ သုံးရန် /start နှိပ်ပါ\n")


    # Help requests
    elif any(word in message_lower for word in ["help", "ကူညီ", "အကူအညီ", "မသိ", "လမ်းညွှန်"]):
        return ("📱 ***အသုံးပြုနိုင်တဲ့ commands:***\n\n"
                "• /start - Bot စတင်အသုံးပြုရန်\n"
                "• /mmb gameid serverid amount - Diamond ဝယ်ယူရန်\n"
                "• /balance - လက်ကျန်ငွေ စစ်ရန်\n"
                "• /topup amount - ငွေဖြည့်ရန်\n"
                "• /price - ဈေးနှုန်းများ ကြည့်ရန်\n"
                "• /history - မှတ်တမ်းများ ကြည့်ရန်\n\n"
                "💡 အသေးစိတ် လိုအပ်ရင် admin ကို ဆက်သွယ်ပါ!")

    # Default response
    else:
        return ("📱 ***MLBB Diamond Top-up Bot***\n\n"
                "💎 ***Diamond ဝယ်ယူရန် /mmb command သုံးပါ။***\n"
                "💰 ***ဈေးနှုန်းများ သိရှိရန် /price နှိပ်ပါ။***\n"
                "🆘 ***အကူအညီ လိုရင် /start နှိပ်ပါ။***")

# --- Price Functions (Using DB) ---

def load_prices():
    """Load custom prices from DB"""
    return db.load_prices()

def save_prices(prices):
    """Save prices to DB"""
    db.save_prices(prices)

# --- Validation Functions ---

def validate_game_id(game_id):
    """Validate MLBB Game ID (6-10 digits)"""
    if not game_id.isdigit():
        return False
    if len(game_id) < 6 or len(game_id) > 10:
        return False
    return True
#__________________PUBG ID FUNCTION__________________________________#

def validate_pubg_id(player_id):
    """Validate PUBG Player ID (7-11 digits)"""
    if not player_id.isdigit():
        return False
    if len(player_id) < 7 or len(player_id) > 11:
        return False
    return True

def get_pubg_price(uc_amount):
    """PUBG UC အတွက် ဈေးနှုန်းကို ရှာပါ။"""
    custom_prices = db.load_pubg_prices() # DB function အသစ်ကို ခေါ်ပါ
    if uc_amount in custom_prices:
        return custom_prices[uc_amount]

    # (Default ဈေးနှုန်းများ - ကိုကို ကြိုက်သလို ဒီမှာ ပြင်နိုင်ပါတယ်)
    table = {
        "60uc": 1500,
        "325uc": 7500,
        "660uc": 15000,
        "1800uc": 37500,
        "3850uc": 75000,
        "8100uc": 150000,
    }
    return table.get(uc_amount)

#__________________PUBG ID FUNCTION__________________________________#

def validate_server_id(server_id):
    """Validate MLBB Server ID (3-5 digits)"""
    if not server_id.isdigit():
        return False
    if len(server_id) < 3 or len(server_id) > 5:
        return False
    return True

def is_banned_account(game_id):
    """Check if MLBB account is banned (example implementation)"""
    banned_ids = [
        "123456789",  # Example banned ID
        "000000000",  # Invalid pattern
        "111111111",  # Invalid pattern
    ]
    if game_id in banned_ids:
        return True
    if len(set(game_id)) == 1:  # All same digits
        return True
    if game_id.startswith("000") or game_id.endswith("000"):
        return True
    return False

def get_price(diamonds):
    """Get price for diamond amount, checking custom prices first"""
    custom_prices = load_prices()
    if diamonds in custom_prices:
        return custom_prices[diamonds]

    # Default prices
    if diamonds.startswith("wp") and diamonds[2:].isdigit():
        n = int(diamonds[2:])
        if 1 <= n <= 10:
            return n * 6000
    table = {
        "11": 950, "22": 1900, "33": 2850, "56": 4200, "112": 8200,
        "86": 5100, "172": 10200, "257": 15300, "343": 20400,
        "429": 25500, "514": 30600, "600": 35700, "706": 40800,
        "878": 51000, "963": 56100, "1049": 61200, "1135": 66300,
        "1412": 81600, "2195": 122400, "3688": 204000,
        "5532": 306000, "9288": 510000, "12976": 714000,
        "55": 3500, "165": 10000, "275": 16000, "565": 33000
    }
    return table.get(diamonds)

def is_payment_screenshot(update):
    """Basic check if a message contains a photo (likely a screenshot)"""
    if update.message.photo:
        return True
    return False

# --- Bot State Check Functions ---

async def check_pending_topup(user_id):
    """Check if user has pending topups in DB"""
    user_data = db.get_user(user_id)
    if not user_data:
        return False
    
    for topup in user_data.get("topups", []):
        if topup.get("status") == "pending":
            return True
    return False

async def send_pending_topup_warning(update: Update):
    """Send pending topup warning message"""
    await update.message.reply_text(
        "⏳ ***Pending Topup ရှိနေပါတယ်!***\n\n"
        "❌ သင့်မှာ admin က approve မလုပ်သေးတဲ့ topup ရှိနေပါတယ်။\n\n"
        "***လုပ်ရမည့်အရာများ***:\n"
        "***• Admin က topup ကို approve လုပ်ပေးတဲ့အထိ စောင့်ပါ။***\n"
        "***• Approve ရပြီးမှ command တွေကို ပြန်အသုံးပြုနိုင်ပါမယ်။***\n\n"
        "📞 ***အရေးပေါ်ဆိုရင် admin ကို ဆက်သွယ်ပါ။***\n\n"
        "💡 /balance ***နဲ့ status စစ်ကြည့်နိုင်ပါတယ်။***",
        parse_mode="Markdown"
    )

async def check_maintenance_mode(command_type):
    """Check if specific command type is in maintenance mode (uses g_settings)"""
    return g_settings.get("maintenance", {}).get(command_type, True)

async def send_maintenance_message(update: Update, command_type):
    """Send maintenance mode message with beautiful UI"""
    user_name = update.effective_user.first_name or "User"

    if command_type == "orders":
        msg = (
            f"မင်္ဂလာပါ {user_name}! 👋\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏸️ ***Bot အော်ဒါတင်ခြင်းအား ခေတ္တ ယာယီပိတ်ထားပါသည်** ⏸️***\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "***🔄 Admin မှ ပြန်လည်ဖွင့်ပေးမှ အသုံးပြုနိုင်ပါမည်။***\n\n"
            "📞 အရေးပေါ်ဆိုရင် Admin ကို ဆက်သွယ်ပါ။"
        )
    elif command_type == "topups":
        msg = (
            f"မင်္ဂလာပါ {user_name}! 👋\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏸️ ***Bot ငွေဖြည့်ခြင်းအား ခေတ္တ ယာယီပိတ်ထားပါသည်*** ⏸️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "***🔄 Admin မှ ပြန်လည်ဖွင့်ပေးမှ အသုံးပြုနိုင်ပါမည်။***\n\n"
            "📞 ***အရေးပေါ်ဆိုရင် Admin ကို ဆက်သွယ်ပါ။***"
        )
    else:
        msg = (
            f"***မင်္ဂလာပါ*** {user_name}! 👋\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏸️ ***Bot အား ခေတ္တ ယာယီပိတ်ထားပါသည်*** ⏸️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "***🔄 Admin မှ ပြန်လည်ဖွင့်ပေးမှ အသုံးပြုနိုင်ပါမည်။***\n\n"
            "📞 ***အရေးပေါ်ဆိုရင် Admin ကို ဆက်သွယ်ပါ။***"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")

# --- User Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    username = user.username or "-"
    name = f"{user.first_name} {user.last_name or ''}".strip()

    load_authorized_users() # 1. Auth list ကို အရင် load လုပ်ပါ
    
    # 2. Referrer ID ကို ဖမ်းပါ
    referrer_id = context.args[0] if context.args else None
    if referrer_id and str(referrer_id) == user_id:
        referrer_id = None

    is_authorized = is_user_authorized(user_id)
    is_new_user_via_referral = (not is_authorized and referrer_id is not None)


    if is_new_user_via_referral:

        print(f"New user {user_id} joined via referral from {referrer_id}. Auto-approving.")
        db.add_authorized_user(user_id) 
        load_authorized_users() 
        is_authorized = True 
        
    elif not is_authorized:
  
        keyboard = [
            [InlineKeyboardButton("📝 Register တောင်းဆိုမယ်", callback_data="request_register")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🚫 ***Bot အသုံးပြုခွင့် မရှိပါ!***\n\n"
            f"👋 ***မင်္ဂလာပါ*** `{name}`!\n"
            f"🆔 Your ID: `{user_id}`\n\n"
            "❌ ***သင်သည် ဤ bot ကို အသုံးပြုခွင့် မရှိသေးပါ။***\n\n"
            "***လုပ်ရမည့်အရာများ***:\n"
            "***• အောက်က 'Register တောင်းဆိုမယ်' button ကို နှိပ်ပါ***\n"
            "***• သို့မဟုတ်*** /register ***command သုံးပါ။***\n\n"
            "✅ ***Owner က approve လုပ်ပြီးမှ bot ကို အသုံးပြုနိုင်ပါမယ်။***\n\n",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return
    # --- (Logic ပြီး) ---

    # 4. Pending Topup စစ်ဆေးပါ (User က သုံးခွင့်ရှိနေပါပြီ)
    if await check_pending_topup(user_id):
        await send_pending_topup_warning(update)
        return

    # 5. User ကို DB ထဲမှာ ဖန်တီးပါ
    user_doc = db.get_user(user_id)
    user_doc = db.get_user(user_id)
    # 5. User ကို DB ထဲမှာ ဖန်တီးပါ
    user_doc = db.get_user(user_id)
    if not user_doc:
        # User အသစ်ဖြစ်မှသာ referrer_id ကို DB ထဲ ထည့်သိမ်းပါ
        db.create_user(user_id, name, username, referrer_id)
        
        # (Referrer ကို အကြောင်းကြားစာ ပို့ပါ)
        if referrer_id: # (Auto-approve ဖြစ်ခဲ့တဲ့ user အတွက်)
            try:
                # --- (ပြင်ဆင်ပြီး) % ကို g_settings ကနေ ယူပါ ---
                current_percentage = g_settings.get("affiliate", {}).get("percentage", 0.03) * 100
                
                referrer_info = db.get_user(referrer_id)
                if referrer_info:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 **Referral အသစ်!**\n\n"
                             f"👤 [{name}](tg://user?id={user_id}) က သင့် link မှတဆင့် bot ကို join လိုက်ပါပြီ။\n"
                             f"သူ order တင်တိုင်း {current_percentage:.0f}% commission ရရှိပါမယ်!",
                        parse_mode="Markdown"
                    )
            except Exception as e:
                print(f"Error notifying referrer: {e}")
    else:
        # --- (!!! ဒီ 'ELSE' BLOCK အသစ်ကို ထပ်ထည့်ပါ !!!) ---
        # User အဟောင်းဖြစ်ပါက Name နှင့် Username ကို DB တွင် Update လုပ်ပါ
        db.update_user_profile(user_id, name, username)
        # --- (ပြီး) ---

    if user_id in user_states:
        del user_states[user_id]

    clickable_name = f"[{name}](tg://user?id={user_id})"
    
    # 6. Welcome Message ပို့ပါ
    if is_new_user_via_referral:
        # (Auto-Approve ဖြစ်သွားတဲ့ User အသစ်အတွက် Message)
        await update.message.reply_text(
            f"🎉 **Welcome!** 🎉\n\n"
            f"👋 မင်္ဂလာပါ {clickable_name}!\n\n"
            f"သင့်သူငယ်ချင်းရဲ့ link ကနေ ဝင်လာတဲ့အတွက် bot ကို **Auto-Approve** လုပ်ပေးလိုက်ပါပြီရှင့်။\n\n"
            "✅ ယခုအခါ bot ကို စတင် အသုံးပြုနိုင်ပါပြီ။\n"
            "💎 Order တင်ရန် /mmb နှိပ်ပါ\n"
            "💰 ငွေဖြည့်ရန် /topup နှိပ်ပါ",
            parse_mode="Markdown"
        )
    else:
        # (User အဟောင်းတွေအတွက် Message)
        # --- (ပြင်ဆင်ပြီး) % ကို g_settings ကနေ ယူပါ ---
        current_percentage = g_settings.get("affiliate", {}).get("percentage", 0.03) * 100
        msg = (
            f"👋 ***မင်္ဂလာပါ*** {clickable_name}!\n"
            f"🆔 ***Telegram User ID:*** `{user_id}`\n\n"
            "💎 *** 𝙅𝘽 𝙈𝙇𝘽𝘽 𝘼𝙐𝙏𝙊 𝙏𝙊𝙋 𝙐𝙋 𝘽𝙊𝙏*** မှ ကြိုဆိုပါတယ်။\n\n"
            "***အသုံးပြုနိုင်တဲ့ command များ***:\n"
            "➤ /mmb gameid serverid amount\n"
            "➤ /balance - ဘယ်လောက်လက်ကျန်ရှိလဲ စစ်မယ်\n"
            "➤ /topup amount - ငွေဖြည့်မယ် (screenshot တင်ပါ)\n"
            "➤ /price - Diamond များရဲ့ ဈေးနှုန်းများ\n"
            "➤ /history - အော်ဒါမှတ်တမ်းကြည့်မယ်\n"
            f"➤ /affiliate - လူရှာပြီး ကော်မရှင်ခ ရယူပါ။\n\n" 
            "***📌 ဥပမာ***:\n"
            "`/mmb 123456789 12345 wp1`\n\n"
            "***လိုအပ်တာရှိရင် Owner ကို ဆက်သွယ်နိုင်ပါတယ်။***"
        )
        try:
            user_photos = await context.bot.get_user_profile_photos(user_id=int(user_id), limit=1)
            if user_photos.total_count > 0:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=user_photos.photos[0][0].file_id,
                    caption=msg,
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(msg, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(msg, parse_mode="Markdown")

async def mmb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_doc = db.get_user(user_id) # User info အရင်ယူထား

    load_authorized_users()
    if not is_user_authorized(user_id):
        keyboard = [[InlineKeyboardButton("👑 Contact Owner", url=f"tg://user?id={ADMIN_ID}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🚫 အသုံးပြုခွင့် မရှိပါ!\n\nOwner ထံ bot အသုံးပြုခွင့် တောင်းဆိုပါ။",
            reply_markup=reply_markup
        )
        return

    if not await check_maintenance_mode("orders"):
        await send_maintenance_message(update, "orders")
        return

    if user_id in user_states and user_states[user_id] == "waiting_approval":
        await update.message.reply_text(
            "⏳ ***Screenshot ပို့ပြီးပါပြီ!***\n\n"
            "❌ ***Admin က လက်ခံပြီးကြောင်း အတည်ပြုတဲ့အထိ commands တွေ အသုံးပြုလို့ မရပါ။***\n\n"
            "⏰ ***Admin က approve လုပ်ပြီးမှ ပြန်လည် အသုံးပြုနိုင်ပါမယ်။***\n"
            "📞 ***အရေးပေါ်ဆိုရင် admin ကို ဆက်သွယ်ပါ။***",
            parse_mode="Markdown"
        )
        return

    if await check_pending_topup(user_id):
        await send_pending_topup_warning(update)
        return

    if user_id in pending_topups:
        await update.message.reply_text(
            "⏳ ***Topup လုပ်ငန်းစဉ် အရင်ပြီးဆုံးပါ!***\n\n"
            "❌ ***လက်ရှိ topup လုပ်ငန်းစဉ်ကို မပြီးသေးပါ။***\n\n"
            "***လုပ်ရမည့်အရာများ***:\n"
            "***• Payment app ရွေးပြီး screenshot တင်ပါ***\n"
            "***• သို့မဟုတ် /cancel နှိပ်ပြီး ပယ်ဖျက်ပါ***\n\n"
            "💡 ***Topup ပြီးမှ order တင်နိုင်ပါမယ်။***",
            parse_mode="Markdown"
        )
        return

    # --- (ပြင်ဆင်ပြီး) Multi-Item Logic ---
    args = context.args
    if len(args) < 3: # အနည်းဆုံး ID, Server, Item 1 ခု ပါရမယ်
        await update.message.reply_text(
            "❌ အမှားရှိပါတယ်!\n\n"
            "***Format***:\n"
            "`/mmb gameid serverid item1 item2 ...`\n\n"
            "***ဥပမာ (၁ ခုတည်း)***:\n"
            "`/mmb 12345678 1234 wp1`\n\n"
            "***ဥပမာ (၂ ခု နှင့်အထက် တွဲဝယ်ရန်)***:\n"
            "`/mmb 12345678 1234 wp1 86`\n"
            "`/mmb 12345678 1234 wp1 wp1 172`",
            parse_mode="Markdown"
        )
        return

    game_id = args[0]
    server_id = args[1]
    items_requested = args[2:] # နောက်ကပါသမျှ item တွေကို list အဖြစ်ယူမယ်

    if not validate_game_id(game_id):
        await update.message.reply_text("❌ ***Game ID မှားနေပါတယ်!*** (6-10 digits)")
        return

    if not validate_server_id(server_id):
        await update.message.reply_text("❌ ***Server ID မှားနေပါတယ်!*** (3-5 digits)")
        return

    if is_banned_account(game_id):
        await update.message.reply_text("🚫 ***Account Ban ဖြစ်နေပါတယ်!***")
        return

    # --- ဈေးနှုန်း တွက်ချက်ခြင်း (Loop) ---
    total_price = 0
    valid_items_list = []

    for item in items_requested:
        item_price = get_price(item)
        if not item_price:
            await update.message.reply_text(
                f"❌ Item မှားနေပါတယ်: `{item}`\n\n"
                "💎 /price နှိပ်ပြီး ဈေးနှုန်းများ ပြန်ကြည့်ပါ။",
                parse_mode="Markdown"
            )
            return
        total_price += item_price
        valid_items_list.append(item)

    # DB မှာ သိမ်းဖို့ Item တွေကို ပေါင်းရေး (Example: "wp1 + 86")
    amount_str = " + ".join(valid_items_list)

    user_balance = user_doc.get("balance", 0)

    if user_balance < total_price:
        keyboard = [[InlineKeyboardButton("💳 ငွေဖြည့်မယ်", callback_data="topup_button")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"❌ ***လက်ကျန်ငွေ မလုံလောက်ပါ!***\n\n"
            f"💎 ***Items***: `{amount_str}`\n"
            f"💰 ***ကျသင့်ငွေ***: {total_price:,} MMK\n"
            f"💳 ***လက်ကျန်***: {user_balance:,} MMK\n"
            f"❗ ***လိုငွေ***: {total_price - user_balance:,} MMK\n\n"
            "***ငွေဖြည့်ရန်*** `/topup amount` ***သုံးပါ။***",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
    order = {
        "order_id": order_id,
        "game_id": game_id,
        "server_id": server_id,
        "amount": amount_str, # "wp1 + 86" ပုံစံဖြင့် သိမ်းမည်
        "price": total_price,
        "status": "pending",
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "chat_id": update.effective_chat.id
    }

    db.update_balance(user_id, -total_price)
    db.add_order(user_id, order)
    new_balance = user_balance - total_price

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"order_confirm_{order_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"order_cancel_{order_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    user_name = f"{update.effective_user.first_name} {update.effective_user.last_name or ''}".strip()
    
    # --- Admin Message ---
    admin_msg = (
        f"🔔 ***အော်ဒါအသစ်ရောက်ပါပြီ!*** (Multi-Item)\n\n"
        f"📝 **Order ID:** `{order_id}`\n"
        f"👤 **User Name:** {user_name}\n\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"🎮 **Game ID:** `{game_id}`\n"
        f"🌐 **Server ID:** `{server_id}`\n"
        f"💎 **Items:** `{amount_str}`\n"
        f"💰 **Total Price:** {total_price:,} MMK\n"
        f"⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📊 **Status:** ⏳ `စောင့်ဆိုင်းနေသည်`"
    )

    load_admin_ids_global()
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_msg,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except:
            pass

    try:
        if await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID):
            # --- Group Message ---
            group_msg = (
                f"🔔 ***အော်ဒါအသစ်ရောက်ပါပြီ!***\n\n"
                f"📝 **Order ID:** `{order_id}`\n"
                f"👤 **User Name:** [{user_name}](tg://user?id={user_id})\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"🎮 **Game ID:** `{game_id}`\n"
                f"🌐 **Server ID:** `{server_id}`\n"
                f"💎 **Items:** `{amount_str}`\n"
                f"💰 **Price:** {total_price:,} MMK\n"
                f"⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📊 **Status:** ⏳ `စောင့်ဆိုင်းနေသည်`\n\n"
                f"#NewOrder"
            )
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID, 
                text=group_msg, 
                parse_mode="Markdown",
                reply_markup=reply_markup 
            )
    except Exception as e:
        print(f"Error sending to admin group: {e}")
        pass

    await update.message.reply_text(
        f"✅ ***အော်ဒါ အောင်မြင်ပါပြီ!***\n\n"
        f"📝 ***Order ID:*** `{order_id}`\n"
        f"🎮 ***Game ID:*** `{game_id} ({server_id})`\n"
        f"💎 ***Items:*** `{amount_str}`\n"
        f"💰 ***ကုန်ကျစရိတ်:*** {total_price:,} MMK\n"
        f"💳 ***လက်ကျန်ငွေ:*** {new_balance:,} MMK\n"
        f"📊 Status: ⏳ ***စောင့်ဆိုင်းနေသည်***\n\n"
        "⚠️ ***Admin က confirm လုပ်ပြီးမှ diamonds များ ရရှိပါမယ်။***",
        parse_mode="Markdown"
    )

#__________________PUBG price FUNCTION__________________________________#

async def pubg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_doc = db.get_user(user_id) 

    load_authorized_users()
    if not is_user_authorized(user_id):
        await update.message.reply_text("🚫 အသုံးပြုခွင့် မရှိပါ!\n\n/start နှိပ်ပြီး Register လုပ်ပါ။")
        return

    if not await check_maintenance_mode("orders"):
        await send_maintenance_message(update, "orders")
        return

    if user_id in user_states and user_states[user_id] == "waiting_approval":
        await update.message.reply_text("⏳ ***Screenshot ပို့ပြီးပါပြီ!***\n\n❌ ***Admin approve မလုပ်မချင်း Order အသစ် တင်လို့မရပါ။***", parse_mode="Markdown")
        return

    if await check_pending_topup(user_id):
        await send_pending_topup_warning(update)
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "❌ ***အမှားရှိပါတယ်!***\n\n"
            "***မှန်ကန်တဲ့ format***:\n"
            "`/pubg <player_id> <amount>`\n\n"
            "***ဥပမာ***:\n"
            "`/pubg 123456789 60uc`",
            parse_mode="Markdown"
        )
        return

    player_id, amount = args
    amount = amount.lower() # 60UC လို့ ရိုက်လည်း 60uc ဖြစ်အောင်

    if not validate_pubg_id(player_id):
        await update.message.reply_text(
            "❌ ***PUBG Player ID မှားနေပါတယ်!*** (ဂဏန်း 7-11 လုံး)\n\n"
            "***ဥပမာ***: `123456789`",
            parse_mode="Markdown"
        )
        return

    price = get_pubg_price(amount)
    if not price:
        await update.message.reply_text(
            f"❌ ***UC Amount မှားနေပါတယ်!***\n\n"
            f"`{amount}` ဆိုတာ မရောင်းပါဘူးရှင့်။ ဥပမာ: `60uc`",
            parse_mode="Markdown"
        )
        return

    user_balance = user_doc.get("balance", 0)

    if user_balance < price:
        await update.message.reply_text(
            f"❌ ***လက်ကျန်ငွေ မလုံလောက်ပါ!***\n\n"
            f"💰 ***လိုအပ်တဲ့ငွေ***: {price:,} MMK\n"
            f"💳 ***သင့်လက်ကျန်***: {user_balance:,} MMK\n\n"
            "***ငွေဖြည့်ရန်*** `/topup amount` ***သုံးပါ။***",
            parse_mode="Markdown"
        )
        return

    order_id = f"PUBG{datetime.now().strftime('%Y%m%d%H%M%S')}"
    order = {
        "order_id": order_id,
        "game": "PUBG",
        "player_id": player_id,
        "amount": amount,
        "price": price,
        "status": "pending",
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "chat_id": update.effective_chat.id
    }

    db.update_balance(user_id, -price)
    db.add_order(user_id, order) # Order မှတ်တမ်းထဲ ထည့်
    new_balance = user_balance - price

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm (PUBG)", callback_data=f"pubg_confirm_{order_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"order_cancel_{order_id}") # Cancel က MLBB နဲ့ အတူတူ သုံးလို့ရ
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    user_name = f"{update.effective_user.first_name} {update.effective_user.last_name or ''}".strip()
    admin_msg = (
        f"🔔 ***PUBG UC Order အသစ်!***\n\n"
        f"📝 ***Order ID:*** `{order_id}`\n"
        f"👤 ***User Name:*** [{user_name}](tg://user?id={user_id})\n\n"
        f"🆔 ***User ID:*** `{user_id}`\n"
        f"🎮 ***Player ID:*** `{player_id}`\n"
        f"💎 ***Amount:*** {amount}\n"
        f"💰 ***Price:*** {price:,} MMK\n"
        f"📊 Status: ⏳ ***စောင့်ဆိုင်းနေသည်***"
    )

    load_admin_ids_global()
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id, text=admin_msg,
                parse_mode="Markdown", reply_markup=reply_markup
            )
        except: pass

    try:
        if await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID):
            group_msg = admin_msg + "\n#NewOrder #PUBG"
            msg_obj = await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=group_msg, parse_mode="Markdown")
            
            db.add_message_to_delete_queue(msg_obj.message_id, msg_obj.chat_id, datetime.now().isoformat())
    except Exception as e:
        print(f"Error sending to admin group in pubg_command: {e}")
        pass

    await update.message.reply_text(
        f"✅ ***PUBG UC အော်ဒါ အောင်မြင်ပါပြီ!***\n\n"
        f"📝 ***Order ID:*** `{order_id}`\n"
        f"🎮 ***Player ID:*** `{player_id}`\n"
        f"💎 ***UC:*** {amount}\n"
        f"💰 ***ကုန်ကျစရိတ်:*** {price:,} MMK\n"
        f"💳 ***လက်ကျန်ငွေ:*** {new_balance:,} MMK\n"
        f"📊 Status: ⏳ ***စောင့်ဆိုင်းနေသည်***\n\n"
        "⚠️ ***Admin က confirm လုပ်ပြီးမှ UC များ ရရှိပါမယ်။***",
        parse_mode="Markdown"
    )

#__________________PUBG price FUNCTION__________________________________#

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = update.effective_user
    name = f"{user.first_name} {user.last_name or ''}".strip()
    username = user.username or "-"
    db.update_user_profile(user_id, name, username)
    # --- (ပြီး) ---

    load_authorized_users()
    if not is_user_authorized(user_id):
        keyboard = [[InlineKeyboardButton("👑 Contact Owner", url=f"tg://user?id={ADMIN_ID}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🚫 အသုံးပြုခွင့် မရှိပါ!\n\nOwner ထံ bot အသုံးပြုခွင့် တောင်းဆိုပါ။",
            reply_markup=reply_markup
        )
        return

    if user_id in user_states and user_states[user_id] == "waiting_approval":
        await update.message.reply_text(
            "⏳ ***Screenshot ပို့ပြီးပါပြီ!***\n\n"
            "❌ ***Admin က လက်ခံပြီးကြောင်း အတည်ပြုတဲ့အထိ commands တွေ အသုံးပြုလို့ မရပါ။***",
            parse_mode="Markdown"
        )
        return

    if user_id in pending_topups:
        await update.message.reply_text(
            "⏳ ***Topup လုပ်ငန်းစဉ် ဆက်လက်လုပ်ဆောင်ပါ!***\n\n"
            "❌ ***လက်ရှိ topup လုပ်ငန်းစဉ်ကို မပြီးသေးပါ။***\n\n"
            "***• Screenshot တင်ပါ***\n"
            "***• သို့မဟုတ် /cancel နှိပ်ပြီး ပယ်ဖျက်ပါ***",
            parse_mode="Markdown"
        )
        return

    if await check_pending_topup(user_id):
        await send_pending_topup_warning(update)
        return

    user_data = db.get_user(user_id)
    if not user_data:
        await update.message.reply_text("❌ အရင်ဆုံး /start နှိပ်ပါ။")
        return

    balance = user_data.get("balance", 0)
    total_orders = len(user_data.get("orders", []))
    total_topups = len(user_data.get("topups", []))

    pending_topups_count = 0
    pending_amount = 0
    for topup in user_data.get("topups", []):
        if topup.get("status") == "pending":
            pending_topups_count += 1
            pending_amount += topup.get("amount", 0)

    name = user_data.get('name', 'Unknown').replace('*', '').replace('_', '').replace('`', '')
    username = user_data.get('username', 'None').replace('*', '').replace('_', '').replace('`', '')

    status_msg = ""
    if pending_topups_count > 0:
        status_msg = f"\n⏳ ***Pending Topups***: {pending_topups_count} ခု ({pending_amount:,} MMK)\n❗ ***Admin approve စောင့်ပါ။***"

    keyboard = [[InlineKeyboardButton("💳 ငွေဖြည့်မယ်", callback_data="topup_button")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    balance_text = (
        f"💳 ***သင့်ရဲ့ Account အချက်အလက်များ***\n\n"
        f"💰 ***လက်ကျန်ငွေ***: `{balance:,} MMK`\n"
        f"📦 ***စုစုပေါင်း အော်ဒါများ***: {total_orders}\n"
        f"💳 ***စုစုပေါင်း ငွေဖြည့်မှုများ***: {total_topups}{status_msg}\n\n"
        f"***👤 နာမည်***: {name}\n"
        f"***🆔 Username***: @{username}"
    )

    try:
        user_photos = await context.bot.get_user_profile_photos(user_id=int(user_id), limit=1)
        if user_photos.total_count > 0:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=user_photos.photos[0][0].file_id,
                caption=balance_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                balance_text, parse_mode="Markdown", reply_markup=reply_markup
            )
    except:
        await update.message.reply_text(
            balance_text, parse_mode="Markdown", reply_markup=reply_markup
        )

async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    load_authorized_users()
    if not is_user_authorized(user_id):
        keyboard = [[InlineKeyboardButton("👑 Contact Owner", url=f"tg://user?id={ADMIN_ID}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🚫 အသုံးပြုခွင့် မရှိပါ!\n\nOwner ထံ bot အသုံးပြုခွင့် တောင်းဆိုပါ။",
            reply_markup=reply_markup
        )
        return

    if not await check_maintenance_mode("topups"):
        await send_maintenance_message(update, "topups")
        return

    if user_id in user_states and user_states[user_id] == "waiting_approval":
        await update.message.reply_text(
            "⏳ ***Screenshot ပို့ပြီးပါပြီ!***\n\n"
            "❌ ***Admin က လက်ခံပြီးကြောင်း အတည်ပြုတဲ့အထိ commands တွေ အသုံးပြုလို့ မရပါ။***",
            parse_mode="Markdown"
        )
        return

    if await check_pending_topup(user_id):
        await send_pending_topup_warning(update)
        return

    if user_id in pending_topups:
        await update.message.reply_text(
            "⏳ ***Topup လုပ်ငန်းစဉ် ဆက်လက်လုပ်ဆောင်ပါ!***\n\n"
            "❌ ***လက်ရှိ topup လုပ်ငန်းစဉ်ကို မပြီးသေးပါ။***\n\n"
            "***• Screenshot တင်ပါ***\n"
            "***• သို့မဟုတ် /cancel နှိပ်ပြီး ပယ်ဖျက်ပါ***",
            parse_mode="Markdown"
        )
        return

    args = context.args
    if len(args) != 1:
        await update.message.reply_text(
            "❌ ***အမှားရှိပါတယ်!***\n\n"
            "***မှန်ကန်တဲ့ format***: `/topup <amount>`\n\n"
            "**ဥပမာ**: `/topup 5000`\n\n"
            "💡 ***အနည်းဆုံး 1,000 MMK ဖြည့်ရပါမည်။***",
            parse_mode="Markdown"
        )
        return

    try:
        amount = int(args[0])
        if amount < 1000:
            await update.message.reply_text(
                "❌ ***ငွေပမာဏ နည်းလွန်းပါတယ်!***\n\n"
                "💰 ***အနည်းဆုံး 1,000 MMK ဖြည့်ရပါမည်။***",
                parse_mode="Markdown"
            )
            return
    except ValueError:
        await update.message.reply_text(
            "❌ ***ငွေပမာဏ မှားနေပါတယ်!***\n\n"
            "***ဥပမာ***: `/topup 5000`",
            parse_mode="Markdown"
        )
        return

    pending_topups[user_id] = {
        "amount": amount,
        "timestamp": datetime.now().isoformat()
    }

    keyboard = [
        [InlineKeyboardButton("📱 KBZ Pay", callback_data=f"topup_pay_kpay_{amount}")],
        [InlineKeyboardButton("📱 Wave Money", callback_data=f"topup_pay_wave_{amount}")],
        [InlineKeyboardButton("❌ ငြင်းပယ်မယ်", callback_data="topup_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"💳 ***ငွေဖြည့်လုပ်ငန်းစဉ်***\n\n"
        f"***✅ ပမာဏ***: `{amount:,} MMK`\n\n"
        f"***အဆင့် 1***: Payment method ရွေးချယ်ပါ\n\n"
        f"***⬇️ ငွေလွှဲမည့် app ရွေးချယ်ပါ***:\n\n"
        f"***ℹ️ ပယ်ဖျက်ရန်*** /cancel ***နှိပ်ပါ***",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    load_authorized_users()
    if not is_user_authorized(user_id):
        keyboard = [[InlineKeyboardButton("👑 Contact Owner", url=f"tg://user?id={ADMIN_ID}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🚫 အသုံးပြုခွင့် မရှိပါ!\n\nOwner ထံ bot အသုံးပြုခွင့် တောင်းဆိုပါ။",
            reply_markup=reply_markup
        )
        return

    if user_id in user_states and user_states[user_id] == "waiting_approval":
        await update.message.reply_text(
            "⏳ ***Screenshot ပို့ပြီးပါပြီ!***\n\n"
            "❌ ***Admin က လက်ခံပြီးကြောင်း အတည်ပြုတဲ့အထိ commands တွေ အသုံးပြုလို့ မရပါ။***",
            parse_mode="Markdown"
        )
        return

    if user_id in pending_topups:
        await update.message.reply_text(
            "⏳ ***Topup လုပ်ငန်းစဉ် ဆက်လက်လုပ်ဆောင်ပါ!***\n\n"
            "❌ ***လက်ရှိ topup လုပ်ငန်းစဉ်ကို မပြီးသေးပါ။***\n\n"
            "***• Screenshot တင်ပါ***\n"
            "***• သို့မဟုတ် /cancel နှိပ်ပြီး ပယ်ဖျက်ပါ***",
            parse_mode="Markdown"
        )
        return

    custom_prices = load_prices() # From DB

    default_prices = {
        "wp1": 6000, "wp2": 12000, "wp3": 18000, "wp4": 24000, "wp5": 30000,
        "wp6": 36000, "wp7": 42000, "wp8": 48000, "wp9": 54000, "wp10": 60000,
        "11": 950, "22": 1900, "33": 2850, "56": 4200, "86": 5100, "112": 8200,
        "172": 10200, "257": 15300, "343": 20400, "429": 25500, "514": 30600,
        "600": 35700, "706": 40800, "878": 51000, "963": 56100, "1049": 61200,
        "1135": 66300, "1412": 81600, "2195": 122400, "3688": 204000,
        "5532": 306000, "9288": 510000, "12976": 714000,
        "55": 3500, "165": 10000, "275": 16000, "565": 33000
    }

    current_prices = {**default_prices, **custom_prices}
    price_msg = "💎 ***MLBB Diamond ဈေးနှုန်းများ***\n\n"

    price_msg += "🎟️ ***Weekly Pass***:\n"
    for i in range(1, 11):
        wp_key = f"wp{i}"
        if wp_key in current_prices:
            price_msg += f"• {wp_key} = {current_prices[wp_key]:,} MMK\n"
    price_msg += "\n"

    price_msg += "💎 ***Regular Diamonds***:\n"
    regular_diamonds = ["11", "22", "33", "56", "86", "112", "172", "257", "343",
                        "429", "514", "600", "706", "878", "963", "1049", "1135",
                        "1412", "2195", "3688", "5532", "9288", "12976"]
    for diamond in regular_diamonds:
        if diamond in current_prices:
            price_msg += f"• {diamond} = {current_prices[diamond]:,} MMK\n"
    price_msg += "\n"

    price_msg += "💎 ***2X Diamond Pass***:\n"
    double_pass = ["55", "165", "275", "565"]
    for dp in double_pass:
        if dp in current_prices:
            price_msg += f"• {dp} = {current_prices[dp]:,} MMK\n"
    price_msg += "\n"

    other_customs = {k: v for k, v in custom_prices.items() if k not in default_prices}
    if other_customs:
        price_msg += "🔥 ***Special Items***:\n"
        for item, price in other_customs.items():
            price_msg += f"• {item} = {price:,} MMK\n"
        price_msg += "\n"

    price_msg += (
        "***📝 အသုံးပြုနည်း***:\n"
        "`/mmb gameid serverid amount`\n\n"
        "***ဥပမာ***:\n"
        "`/mmb 123456789 12345 wp1`\n"
        "`/mmb 123456789 12345 86`"
    )

    await update.message.reply_text(price_msg, parse_mode="Markdown")

async def pubg_price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(User) PUBG UC ဈေးနှုန်းများကို ကြည့်ပါ။"""
    user_id = str(update.effective_user.id)

    load_authorized_users()
    if not is_user_authorized(user_id):
        await update.message.reply_text("🚫 အသုံးပြုခွင့် မရှိပါ!\n\n/start နှိပ်ပြီး Register လုပ်ပါ။")
        return

    if user_id in user_states and user_states[user_id] == "waiting_approval":
        await update.message.reply_text(
            "⏳ ***Screenshot ပို့ပြီးပါပြီ!***\n\n"
            "❌ ***Admin approve မလုပ်မချင်း commands တွေ သုံးလို့မရပါ။***",
            parse_mode="Markdown"
        )
        return

    if user_id in pending_topups:
        await update.message.reply_text(
            "⏳ ***Topup လုပ်ငန်းစဉ် ဆက်လက်လုပ်ဆောင်ပါ!***\n\n"
            "❌ ***လက်ရှိ topup လုပ်ငန်းစဉ်ကို မပြီးသေးပါ။***",
            parse_mode="Markdown"
        )
        return

    custom_prices = db.load_pubg_prices() # From DB

    default_prices = {
        "60uc": 1500, "325uc": 7500, "660uc": 15000,
        "1800uc": 37500, "3850uc": 75000, "8100uc": 150000
    }

    current_prices = {**default_prices, **custom_prices}
    price_msg = "💎 ***PUBG UC ဈေးနှုန်းများ***\n\n"

    # Sort keys (60, 325, 660, ...)
    sorted_keys = sorted(current_prices.keys(), key=lambda x: int(re.sub(r'\D', '', x)))

    for uc in sorted_keys:
        price_msg += f"• {uc} = {current_prices[uc]:,} MMK\n"
    
    price_msg += "\n"
    price_msg += (
        "***📝 အသုံးပြုနည်း***:\n"
        "`/pubg <player_id> <amount>`\n\n"
        "***ဥပမာ***:\n"
        "`/pubg 12345678 60uc`"
    )

    await update.message.reply_text(price_msg, parse_mode="Markdown")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_user_authorized(user_id):
        return

    if user_id in pending_topups:
        del pending_topups[user_id]
        await update.message.reply_text(
            "✅ ***ငွေဖြည့်ခြင်း ပယ်ဖျက်ပါပြီ!***\n\n"
            "💡 ***ပြန်ဖြည့်ချင်ရင်*** /topup ***နှိပ်ပါ။***",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "***ℹ️ လက်ရှိ ငွေဖြည့်မှု လုပ်ငန်းစဉ် မရှိပါ။***",
            parse_mode="Markdown"
        )



async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    load_authorized_users()
    if not is_user_authorized(user_id):
        keyboard = [[InlineKeyboardButton("👑 Contact Owner", url=f"tg://user?id={ADMIN_ID}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🚫 အသုံးပြုခွင့် မရှိပါ!\n\nOwner ထံ bot အသုံးပြုခွင့် တောင်းဆိုပါ။",
            reply_markup=reply_markup
        )
        return

    if user_id in user_states and user_states[user_id] == "waiting_approval":
        await update.message.reply_text(
            "⏳ ***Screenshot ပို့ပြီးပါပြီ!***\n\n"
            "❌ ***Admin က လက်ခံပြီးကြောင်း အတည်ပြုတဲ့အထိ commands တွေ အသုံးပြုလို့ မရပါ။***",
            parse_mode="Markdown"
        )
        return

    if user_id in pending_topups:
        await update.message.reply_text(
            "⏳ ***Topup လုပ်ငန်းစဉ် ဆက်လက်လုပ်ဆောင်ပါ!***\n\n"
            "❌ ***လက်ရှိ topup လုပ်ငန်းစဉ်ကို မပြီးသေးပါ။***",
            parse_mode="Markdown"
        )
        return

    if await check_pending_topup(user_id):
        await send_pending_topup_warning(update)
        return

    user_data = db.get_user(user_id)
    if not user_data:
        await update.message.reply_text("❌ အရင်ဆုံး /start နှိပ်ပါ။")
        return

    orders = db.get_user_orders(user_id, limit=999999999)
    topups = db.get_user_topups(user_id, limit=999999999)

    if not orders and not topups:
        await update.message.reply_text("📋 သင့်မှာ မည်သည့် မှတ်တမ်းမှ မရှိသေးပါ။")
        return

    msg = "📋 သင့်ရဲ့ မှတ်တမ်းများ\n\n"
    if orders:
        msg += "🛒 အော်ဒါများ (နောက်ဆုံး 5 ခု):\n"
        for order in orders:
            status_emoji = "✅" if order.get("status") == "confirmed" else "⏳" if order.get("status") == "pending" else "❌"
            msg += f"{status_emoji} {order['order_id']} - {order['amount']} ({order['price']:,} MMK)\n"
        msg += "\n"

    if topups:
        msg += "💳 ငွေဖြည့်များ (နောက်ဆုံး 5 ခု):\n"
        for topup in topups:
            status_emoji = "✅" if topup.get("status") == "approved" else "⏳" if topup.get("status") == "pending" else "❌"
            msg += f"{status_emoji} {topup['amount']:,} MMK - {topup.get('timestamp', 'Unknown')[:10]}\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

# --- (အသစ်) Affiliate Command ---
async def affiliate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User ၏ referral link နှင့် earnings များကို ပြသပါ။"""
    user = update.effective_user
    user_id = str(user.id)

    if not is_user_authorized(user_id):
        await update.message.reply_text("🚫 အသုံးပြုခွင့် မရှိပါ!\n\n/start နှိပ်ပြီး Register လုပ်ပါ။")
        return
        
    user_doc = db.get_user(user_id)
    if not user_doc:
        await update.message.reply_text("❌ User မတွေ့ပါ။ /start ကို အရင်နှိပ်ပါ။")
        return

    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    
    earnings = user_doc.get("referral_earnings", 0)
    
    # --- (ပြင်ဆင်ပြီး) % ကို g_settings ကနေ ယူပါ ---
    current_percentage = g_settings.get("affiliate", {}).get("percentage", 0.03) * 100

    msg = (
        f"💸 ***Affiliate Program ({current_percentage:.0f}% Commission)***\n\n"
        f"ဒီ bot လေးကို သူငယ်ချင်းတွေဆီ မျှဝေပြီး {current_percentage:.0f}% commission ရယူလိုက်ပါ။\n\n"
        f"**သင်၏ Referral Link:**\n"
        f"`{referral_link}`\n"
        f"(ဒီ link ကို copy ကူးပြီး သူငယ်ချင်းတွေကို ပို့ပေးလိုက်ပါ)\n\n"
        f"--- (သင်၏ မှတ်တမ်း) ---\n"
        f"💰 **စုစုပေါင်း ရရှိငွေ:** `{earnings:,} MMK`\n"
    )
    
    await update.message.reply_text(msg, parse_mode="Markdown")

# --- Admin Command Handlers ---

async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_name = f"{update.effective_user.first_name} {update.effective_user.last_name or ''}".strip()

    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "❌ အမှားရှိပါတယ်!\n\n"
            "မှန်ကန်တဲ့ format: `/approve user_id amount`\n"
            "ဥပမာ: `/approve 123456789 50000`"
        )
        return

    try:
        target_user_id = args[0]
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ ငွေပမာဏမှားနေပါတယ်!")
        return

    user_data = db.get_user(target_user_id)
    if not user_data:
        await update.message.reply_text("❌ User မတွေ့ရှိပါ!")
        return

    topup_id_to_approve = None
    for topup in reversed(user_data.get("topups", [])):
        if topup.get("status") == "pending" and topup.get("amount") == amount:
            topup_id_to_approve = topup.get("topup_id")
            break

    if not topup_id_to_approve:
        await update.message.reply_text(
            f"❌ User `{target_user_id}` မှာ `{amount}` MMK နဲ့ pending topup မတွေ့ပါ!",
            parse_mode="Markdown"
        )
        return

    updates = {
        "status": "approved",
        "approved_by": admin_name,
        "approved_at": datetime.now().isoformat()
    }
    
    approved_user_id = db.find_and_update_topup(topup_id_to_approve, updates) # This also updates balance

    if not approved_user_id:
        await update.message.reply_text("❌ Topup approve လုပ်ရာတွင် အမှားဖြစ်သွားသည်!")
        return

    if target_user_id in user_states:
        del user_states[target_user_id]

    try:
        user_balance = db.get_balance(target_user_id)
        keyboard = [[InlineKeyboardButton("💎 Order တင်မယ်", url=f"https://t.me/{context.bot.username}?start=order")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=int(target_user_id),
            text=f"✅ ***ငွေဖြည့်မှု အတည်ပြုပါပြီ!*** 🎉\n\n"
                 f"💰 ***ပမာဏ:*** `{amount:,} MMK`\n"
                 f"💳 ***လက်ကျန်ငွေ:*** `{user_balance:,} MMK`\n"
                 f"👤 ***Approved by:*** [{admin_name}](tg://user?id={user_id})\n"
                 f"⏰ ***အချိန်:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                 f"🎉 ***ယခုအခါ diamonds များ ဝယ်ယူနိုင်ပါပြီ!***\n"
                 f"🔓 ***Bot လုပ်ဆောင်ချက်များ ပြန်လည် အသုံးပြုနိုင်ပါပြီ!***",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    except:
        pass

    await update.message.reply_text(
        f"✅ ***Approve အောင်မြင်ပါပြီ!***\n\n"
        f"👤 ***User ID:*** `{target_user_id}`\n"
        f"💰 ***Amount:*** `{amount:,} MMK`\n"
        f"💳 ***User's new balance:*** `{db.get_balance(target_user_id):,} MMK`\n"
        f"🔓 ***User restrictions cleared!***",
        parse_mode="Markdown"
    )

async def deduct_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "❌ အမှားရှိပါတယ်!\n\n"
            "မှန်ကန်တဲ့ format: `/deduct user_id amount`\n"
            "ဥပမာ: `/deduct 123456789 10000`"
        )
        return

    try:
        target_user_id = args[0]
        amount = int(args[1])
        if amount <= 0:
            await update.message.reply_text("❌ ငွေပမာဏသည် သုညထက် ကြီးရမည်!")
            return
    except ValueError:
        await update.message.reply_text("❌ ငွေပမာဏမှားနေပါတယ်!")
        return

    if not db.get_user(target_user_id):
        await update.message.reply_text("❌ User မတွေ့ရှိပါ!")
        return

    current_balance = db.get_balance(target_user_id)
    if current_balance < amount:
        await update.message.reply_text(
            f"❌ ***နှုတ်လို့မရပါ!***\n\n"
            f"💰 ***နှုတ်ချင်တဲ့ပမာဏ***: `{amount:,} MMK`\n"
            f"💳 ***User လက်ကျန်ငွေ***: `{current_balance:,} MMK`",
            parse_mode="Markdown"
        )
        return

    db.update_balance(target_user_id, -amount)
    new_balance = db.get_balance(target_user_id)

    try:
        user_msg = (
            f"⚠️ ***လက်ကျန်ငွေ နှုတ်ခံရမှု***\n\n"
            f"💰 ***နှုတ်ခံရတဲ့ပမာဏ***: `{amount:,} MMK`\n"
            f"💳 ***လက်ကျန်ငွေ***: `{new_balance:,} MMK`\n"
            "📞 မေးခွန်းရှိရင် admin ကို ဆက်သွယ်ပါ။"
        )
        await context.bot.send_message(chat_id=int(target_user_id), text=user_msg, parse_mode="Markdown")
    except:
        pass

    await update.message.reply_text(
        f"✅ ***Balance နှုတ်ခြင်း အောင်မြင်ပါပြီ!***\n\n"
        f"👤 User ID: `{target_user_id}`\n"
        f"💰 ***နှုတ်ခဲ့တဲ့ပမာဏ***: `{amount:,} MMK`\n"
        f"💳 ***User လက်ကျန်ငွေ***: `{new_balance:,} MMK`",
        parse_mode="Markdown"
    )

async def addrefund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # 1. Admin ဖြစ်မှ သုံးခွင့်ပြုမည်
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် Admin မဟုတ်ပါ!")
        return

    # 2. Format စစ်ဆေးခြင်း
    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "❌ Format မှားနေပါသည်!\n\n"
            "✅ ***အသုံးပြုပုံ***: `/addrefund <user_id> <amount>`\n"
            "📌 ***ဥပမာ***: `/addrefund 123456789 5000`",
            parse_mode="Markdown"
        )
        return

    target_user_id = args[0]
    
    # 3. Amount မှန်မမှန် စစ်ဆေးခြင်း
    try:
        amount = int(args[1])
        if amount <= 0:
            await update.message.reply_text("❌ ပမာဏသည် 0 ထက် များရပါမည်။")
            return
    except ValueError:
        await update.message.reply_text("❌ ပမာဏကို ဂဏန်းဖြင့်သာ ရိုက်ထည့်ပါ။")
        return

    # 4. User ရှိမရှိ Database တွင် စစ်ဆေးခြင်း
    user_data = db.get_user(target_user_id)
    if not user_data:
        await update.message.reply_text(f"❌ User ID `{target_user_id}` ကို ရှာမတွေ့ပါ။", parse_mode="Markdown")
        return

    # 5. Balance ထည့်သွင်းခြင်း (Database Update)
    db.update_balance(target_user_id, amount)
    new_balance = db.get_balance(target_user_id)

    # 6. Admin ကို အောင်မြင်ကြောင်း ပြန်ပြောခြင်း
    await update.message.reply_text(
        f"✅ **Refund/Balance ဖြည့်သွင်းမှု အောင်မြင်ပါသည်!**\n\n"
        f"👤 User ID: `{target_user_id}`\n"
        f"💰 ဖြည့်သွင်းငွေ: `{amount:,} MMK`\n"
        f"💳 လက်ကျန်ငွေသစ်: `{new_balance:,} MMK`",
        parse_mode="Markdown"
    )

    # 7. User ဆီကို Message လှမ်းပို့ခြင်း
    try:
        await context.bot.send_message(
            chat_id=int(target_user_id),
            text=f"🎁 **Balance ဖြည့်သွင်းခြင်း (Refund/Bonus)**\n\n"
                 f"Admin မှ သင့်အကောင့်သို့ `{amount:,} MMK` ထည့်သွင်းပေးလိုက်ပါသည်။\n\n"
                 f"💳 **လက်ရှိလက်ကျန်**: `{new_balance:,} MMK`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Error notifying user {target_user_id}: {e}")
        await update.message.reply_text("⚠️ User ထံသို့ Message ပို့မရပါ (Bot ကို block ထားခြင်း ဖြစ်နိုင်သည်)။ သို့သော် Balance ဖြည့်ပြီးပါပြီ။")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    if len(args) != 1 or not args[0].isdigit():
        await update.message.reply_text("❌ မှန်ကန်တဲ့အတိုင်း: /done <user_id>")
        return

    target_user_id = int(args[0])
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text="🙏 ဝယ်ယူအားပေးမှုအတွက် ကျေးဇူးအများကြီးတင်ပါတယ်။\n\n✅ Order Done! 🎉"
        )
        await update.message.reply_text("✅ User ထံ message ပေးပြီးပါပြီ။")
    except:
        await update.message.reply_text("❌ User ID မှားနေပါတယ်။ Message မပို့နိုင်ပါ။")

async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    if len(args) < 2 or not args[0].isdigit():
        await update.message.reply_text("❌ မှန်ကန်တဲ့အတိုင်း: /reply <user_id> <message>")
        return

    target_user_id = int(args[0])
    message = " ".join(args[1:])
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=message
        )
        await update.message.reply_text("✅ Message ပေးပြီးပါပြီ။")
    except:
        await update.message.reply_text("❌ Message မပို့နိုင်ပါ။")

async def check_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin Only) User ID ဖြင့် User ၏ Data များကို စစ်ဆေးပါ။"""
    user_id = str(update.effective_user.id)
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    if len(args) != 1:
        await update.message.reply_text("❌ Format မှားနေပါပြီ!\n`/checkuser <user_id>`")
        return
        
    target_user_id = args[0]
    user_data = db.get_user(target_user_id) # DB ထဲက user ကို ရှာပါ

    if not user_data:
        await update.message.reply_text(f"❌ User ID `{target_user_id}` ကို မတွေ့ရှိပါ။")
        return

    # User Data တွေ ထုတ်ပါ
    balance = user_data.get("balance", 0)
    total_orders = len(user_data.get("orders", []))
    total_topups = len(user_data.get("topups", []))
    name = user_data.get('name', 'Unknown').replace('*', '').replace('_', '').replace('`', '')
    username = user_data.get('username', 'None').replace('*', '').replace('_', '').replace('`', '')
    joined_at = user_data.get('joined_at', 'Unknown')[:10]
    
    # (Affiliate Data)
    referred_by = user_data.get('referred_by', 'None')
    referral_earnings = user_data.get('referral_earnings', 0)

    # Pending topup တွေကို စစ်ဆေးပါ
    pending_topups_count = 0
    pending_amount = 0
    for topup in user_data.get("topups", []):
        if topup.get("status") == "pending":
            pending_topups_count += 1
            pending_amount += topup.get("amount", 0)

    status_msg = ""
    if pending_topups_count > 0:
        status_msg = f"\n⏳ ***Pending Topups***: {pending_topups_count} ခု ({pending_amount:,} MMK)"

    # Admin ကို ပြန်ပို့မယ့် Message
    report_msg = (
        f"📊 ***User Data Report***\n"
        f"*(ID: `{target_user_id}`)*\n\n"
        f"👤 ***Name***: {name}\n"
        f"🆔 ***Username***: @{username}\n"
        f"📅 ***Joined***: {joined_at}\n"
        f"--- (Balance) ---\n"
        f"💰 ***လက်ကျန်ငွေ***: `{balance:,} MMK`\n"
        f"📦 ***စုစုပေါင်း အော်ဒါများ***: {total_orders}\n"
        f"💳 ***စုစုပေါင်း ငွေဖြည့်မှုများ***: {total_topups}{status_msg}\n"
        f"--- (Affiliate) ---\n"
        f"💸 ***Commission ရငွေ***: `{referral_earnings:,} MMK`\n"
        f"🔗 ***ခေါ်လာသူ ID***: `{referred_by}`\n"
    )
    
    await update.message.reply_text(report_msg, parse_mode="Markdown")

async def check_all_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner Only) User အားလုံး၏ data များကို list ဖြင့် စစ်ဆေးပါ။"""
    user_id = str(update.effective_user.id)
    
    # Owner (ADMIN_ID) သာ သုံးခွင့်ပြုပါ
    if not is_owner(user_id):
        await update.message.reply_text("❌ ဤ command ကို Bot Owner (ADMIN_ID) တစ်ဦးတည်းသာ အသုံးပြုနိုင်ပါသည်။")
        return

    try:
        all_users = db.get_all_users()
    except Exception as e:
        await update.message.reply_text(f"❌ User data များကို DB မှ ဆွဲထုတ်ရာတွင် Error ဖြစ်နေပါသည်: {e}")
        return

    if not all_users:
        await update.message.reply_text("ℹ️ Bot မှာ User တစ်ယောက်မှ မရှိသေးပါဘူး။")
        return

    await update.message.reply_text(
        f"📊 **All User Report**\n\n"
        f"User စုစုပေါင်း `{len(all_users)}` ယောက်၏ data ကို စတင် စစ်ဆေးပါပြီ။\n"
        f"User အရေအတွက် များပါက message များ ခွဲပို့ပါမည်။ ခဏစောင့်ပါ...",
        parse_mode="Markdown"
    )

    message_chunk = "--- 📊 **All User Data Report** ---\n\n"
    users_count = 0
    
    for user_data in all_users:
        users_count += 1
        
        # DB မှ data များကို ဆွဲထုတ်ပါ
        uid = user_data.get("user_id", "N/A")
        name = user_data.get("name", "Unknown").replace('`', '').replace('*', '') # Markdown error မတက်အောင် clean လုပ်
        balance = user_data.get("balance", 0)
        orders_count = len(user_data.get("orders", []))
        topups_count = len(user_data.get("topups", []))
        commission = user_data.get("referral_earnings", 0) # Affiliate commission
        
        # User တစ်ယောက်ချင်းစီအတွက် စာကြောင်း
        line = (
            f"❖ **{name}** ● `{uid}` ●\n"
            f"  ◈Bᴀʟᴀɴᴄᴇ↝ {balance:,} | ◈Oʀᴅᴇʀ↝ {orders_count} | ◈Tᴏᴘᴜᴘ↝ {topups_count} | ◈Cᴏᴍᴍɪssɪᴏɴ↝ {commission:,}\n"
            f"----------------------------\n"
        )
        
        # Telegram Message Limit (4096) မကျော်အောင် စစ်ဆေးပါ
        if len(message_chunk) + len(line) > 4000:
            # Message အရမ်းရှည်လာရင် အပိုင်းဖြတ်ပြီး ပို့ပါ
            await update.message.reply_text(message_chunk, parse_mode="Markdown")
            # Message အသစ် ပြန်စပါ
            message_chunk = ""
        
        message_chunk += line

    # နောက်ဆုံး ကျန်နေတဲ့ message chunk ကို ပို့ပါ
    if message_chunk:
        await update.message.reply_text(message_chunk, parse_mode="Markdown")
        
    await update.message.reply_text(f"✅ Report ပြီးပါပြီ။ User `{users_count}` ယောက်လုံးကို စစ်ဆေးပြီးပါပြီ။")


async def clean_python_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner Only) .py file များထဲမှ comment များကို ရှင်းလင်းပါ။"""
    user_id = str(update.effective_user.id)
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ ဤ command ကို Bot Owner (ADMIN_ID) တစ်ဦးတည်းသာ အသုံးပြုနိုင်ပါသည်။")
        return

    args = context.args
    if len(args) != 1:
        await update.message.reply_text("❌ Format မှားနေပါပြီ!\n`/cleanpython <file_name.py>`\n\nဥပမာ: `/cleanpython main.py`")
        return
        
    file_name = args[0]
    
    # Security Check (Directory Traversal မဖြစ်အောင် + .py file ဟုတ်မှ)
    if ".." in file_name or not file_name.endswith(".py"):
        await update.message.reply_text("❌ `.py` file များကိုသာ ရှင်းလင်းခွင့်ပြုပါသည်။")
        return
        
    if not os.path.exists(file_name):
        await update.message.reply_text(f"❌ File `{file_name}` ကို မတွေ့ရှိပါ။")
        return

    try:
        cleaned_lines = []
        with open(file_name, 'r', encoding='utf-8') as f:
            for line in f:
                # '#' နဲ့ စတဲ့ comment line တွေကို ဖြုတ်
                if not line.strip().startswith('#'):
                    # Empty line တွေ အရမ်းများမသွားအောင် စာလုံးပါမှ ထည့်
                    if line.strip(): 
                        cleaned_lines.append(line)
        
        cleaned_content = "".join(cleaned_lines)
        
        # ရှင်းလင်းပြီးသား content ကို clean.txt file အဖြစ် ဖန်တီး
        output_filename = "clean.txt"
        with open(output_filename, "w", encoding="utf-8") as out_f:
            out_f.write(f"# --- Cleaned version of {file_name} ---\n\n")
            out_f.write(cleaned_content)
            
        # User ဆီကို file ပြန်ပို့
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(output_filename, "rb"),
            caption=f"✅ `{file_name}` ထဲမှ Comment များ ရှင်းလင်းပြီးပါပြီ။",
            filename=f"clean_{file_name}.txt"
        )
        
        # Server ပေါ်က file အဟောင်းကို ပြန်ဖျက်
        os.remove(output_filename)

    except Exception as e:
        await update.message.reply_text(f"❌ Error ဖြစ်သွားပါသည်: {e}")

async def _send_registration_to_admins(user: User, context: ContextTypes.DEFAULT_TYPE):
    """
    Helper function: Admin များအားလုံးထံ Registration request ကို ပို့ပေးသည်။
    (ဤ function ကို register_command နှင့် button_callback တို့မှ ခေါ်သည်)
    """
    user_id = str(user.id)
    username = user.username or "-"
    name = f"{user.first_name} {user.last_name or ''}".strip()
    
    # Markdown Escape
    def escape_markdown(text):
        chars = r"_*[]()~`>#+-=|{}.!"
        return re.sub(f'([{re.escape(chars)}])', r'\\\1', text)
    username_escaped = escape_markdown(username)

    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"register_approve_{user_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"register_reject_{user_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    owner_msg = (
        f"📝 ***Registration Request***\n\n"
        f"👤 ***User Name:*** [{name}](tg://user?id={user_id})\n"
        f"🆔 ***User ID:*** `{user_id}`\n"
        f"📱 ***Username:*** @{username_escaped}\n\n"
        f"***အသုံးပြုခွင့် ပေးမလား?***"
    )

    try:
        user_photos = await context.bot.get_user_profile_photos(user_id=int(user_id), limit=1)
        photo_id = user_photos.photos[0][0].file_id if user_photos.total_count > 0 else None
        
        load_admin_ids_global() # Admin list ကို DB မှ ပြန်ခေါ်ပါ
        for admin_id in ADMIN_IDS:
            try:
                if photo_id:
                    await context.bot.send_photo(
                        chat_id=admin_id, photo=photo_id, caption=owner_msg,
                        parse_mode="Markdown", reply_markup=reply_markup
                    )
                else:
                    await context.bot.send_message(
                        chat_id=admin_id, text=owner_msg, 
                        parse_mode="Markdown", reply_markup=reply_markup
                    )
            except Exception as e_inner:
                 print(f"Failed to send register request to admin {admin_id}: {e_inner}")
    except Exception as e:
        print(f"Error sending registration request to admins: {e}")

# main.py (ဤ function တစ်ခုလုံးကို အစားထိုးပါ)

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User registration request (command မှ ခေါ်လျှင်)"""
    user = update.effective_user
    user_id = str(user.id)
    
    load_authorized_users()
    if is_user_authorized(user_id):
        await update.message.reply_text("✅ သင်သည် အသုံးပြုခွင့် ရပြီးသား ဖြစ်ပါတယ်!\n\n🚀 /start နှိပ်ပါ။")
        return

    # Call the helper function to send message to admins
    await _send_registration_to_admins(user, context)

    # Send confirmation reply *to the message*
    user_confirm_msg = (
        f"✅ ***Registration တောင်းဆိုမှု ပို့ပြီးပါပြီ!***\n\n"
        f"🆔 ***သင့် User ID:*** `{user_id}`\n\n"
        f"⏳ ***Owner က approve လုပ်တဲ့အထိ စောင့်ပါ။***"
    )
    try:
        # Try to reply with photo
        user_photos = await context.bot.get_user_profile_photos(user_id=int(user_id), limit=1)
        if user_photos.total_count > 0:
            await update.message.reply_photo(
                photo=user_photos.photos[0][0].file_id,
                caption=user_confirm_msg,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(user_confirm_msg, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(user_confirm_msg, parse_mode="Markdown")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_name = f"{update.effective_user.first_name} {update.effective_user.last_name or ''}".strip()

    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    if len(args) != 1 or not args[0].isdigit():
        await update.message.reply_text("❌ မှန်ကန်တဲ့အတိုင်း: /ban <user\\_id>", parse_mode="Markdown")
        return

    target_user_id = args[0]
    load_authorized_users()

    if target_user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("ℹ️ User သည် authorize မလုပ်ထားပါ။")
        return

    db.remove_authorized_user(target_user_id)
    load_authorized_users()

    try:
        await context.bot.send_message(
            chat_id=int(target_user_id),
            text="🚫 Bot အသုံးပြုခွင့် ပိတ်ပင်ခံရမှု\n\n"
                 "❌ Admin က သင့်ကို ban လုပ်လိုက်ပါပြီ။\n\n"
                 "📞 အကြောင်းရင်း သိရှိရန် Admin ကို ဆက်သွယ်ပါ။",
            parse_mode="Markdown"
        )
    except:
        pass

    try:
        user_doc = db.get_user(target_user_id)
        user_name = user_doc.get("name", "Unknown") if user_doc else "Unknown"
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚫 *User Ban Notification*\n\n"
                 f"👤 Admin: [{admin_name}](tg://user?id={user_id})\n"
                 f"🎯 Banned User: [{user_name}](tg://user?id={target_user_id})\n"
                 f"🎯 Banned User ID: `{target_user_id}`",
            parse_mode="Markdown"
        )
    except:
        pass

    try:
        user_doc = db.get_user(target_user_id)
        user_name = user_doc.get("name", "Unknown") if user_doc else "Unknown"
        group_msg = (
            f"🚫 ***User Ban ဖြစ်ပါပြီ!***\n\n"
            f"👤 ***User:*** [{user_name}](tg://user?id={target_user_id})\n"
            f"🆔 ***User ID:*** `{target_user_id}`\n"
            f"👤 ***Ban လုပ်သူ:*** {admin_name}\n"
            f"#UserBanned"
        )
        if await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID):
            msg_obj = await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=group_msg, parse_mode="Markdown")
            
            db.add_message_to_delete_queue(msg_obj.message_id, msg_obj.chat_id, datetime.now().isoformat())
    except Exception as e:
        print(f"Error sending to admin group in ban_command: {e}")
        pass

    await update.message.reply_text(
        f"✅ User Ban အောင်မြင်ပါပြီ!\n\n"
        f"👤 User ID: `{target_user_id}`\n"
        f"📝 Total authorized users: {len(AUTHORIZED_USERS)}",
        parse_mode="Markdown"
    )

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_name = f"{update.effective_user.first_name} {update.effective_user.last_name or ''}".strip()

    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    if len(args) != 1 or not args[0].isdigit():
        await update.message.reply_text("❌ မှန်ကန်တဲ့အတိုင်း: /unban <user\\_id>", parse_mode="Markdown")
        return

    target_user_id = args[0]
    load_authorized_users()

    if target_user_id in AUTHORIZED_USERS:
        await update.message.reply_text("ℹ️ User သည် authorize ပြုလုပ်ထားပြီးပါပြီ။")
        return

    db.add_authorized_user(target_user_id)
    load_authorized_users()

    if target_user_id in user_states:
        del user_states[target_user_id]

    try:
        await context.bot.send_message(
            chat_id=int(target_user_id),
            text="🎉 *Bot အသုံးပြုခွင့် ပြန်လည်ရရှိပါပြီ!*\n\n"
                 "✅ Admin က သင့် ban ကို ဖြုတ်ပေးလိုက်ပါပြီ။\n\n"
                 "🚀 ယခုအခါ /start နှိပ်ပြီး bot ကို အသုံးပြုနိုင်ပါပြီ!",
            parse_mode="Markdown"
        )
    except:
        pass

    try:
        user_doc = db.get_user(target_user_id)
        user_name = user_doc.get("name", "Unknown") if user_doc else "Unknown"
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"✅ *User Unban Notification*\n\n"
                 f"👤 Admin: [{admin_name}](tg://user?id={user_id})\n"
                 f"🎯 Unbanned User: [{user_name}](tg://user?id={target_user_id})\n"
                 f"🎯 Unbanned User ID: `{target_user_id}`",
            parse_mode="Markdown"
        )
    except:
        pass

    try:
        user_doc = db.get_user(target_user_id)
        user_name = user_doc.get("name", "Unknown") if user_doc else "Unknown"
        
        group_msg = (
            f"✅ ***User Unban ဖြစ်ပါပြီ!***\n\n"
            f"👤 ***User:*** [{user_name}](tg://user?id={target_user_id})\n"
            f"🆔 ***User ID:*** `{target_user_id}`\n"
            f"👤 ***Unban လုပ်သူ:*** {admin_name}\n"
            f"#UserUnbanned"
        )
        if await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID):
            msg_obj = await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=group_msg, parse_mode="Markdown")
            
            db.add_message_to_delete_queue(msg_obj.message_id, msg_obj.chat_id, datetime.now().isoformat())
            
    except Exception as e:
        print(f"Error sending to admin group in unban_command: {e}")
        pass

    await update.message.reply_text(
        f"✅ User Unban အောင်မြင်ပါပြီ!\n\n"
        f"👤 User ID: `{target_user_id}`\n"
        f"📝 Total authorized users: {len(AUTHORIZED_USERS)}",
        parse_mode="Markdown"
    )

async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "❌ မှန်ကန်တဲ့အတိုင်း: /maintenance <feature> <on/off>\n\n"
            "Features: `orders`, `topups`, `general`\n"
            "ဥပမာ: `/maintenance orders off`"
        )
        return

    feature = args[0].lower()
    status = args[1].lower()

    if feature not in ["orders", "topups", "general"]:
        await update.message.reply_text("❌ Feature မှားနေပါတယ်! orders, topups, general ထဲမှ ရွေးပါ။")
        return
    if status not in ["on", "off"]:
        await update.message.reply_text("❌ Status မှားနေပါတယ်! on သို့မဟုတ် off ရွေးပါ။")
        return

    new_status = (status == "on")
    
    # Update DB
    db.update_setting(f"maintenance.{feature}", new_status)
    # Reload local settings from DB
    load_global_settings()

    status_text = "🟢 ***ဖွင့်ထား***" if new_status else "🔴 ***ပိတ်ထား***"
    feature_text = {
        "orders": "***အော်ဒါလုပ်ဆောင်ချက်***",
        "topups": "***ငွေဖြည့်လုပ်ဆောင်ချက်***",
        "general": "***ယေဘူယျလုပ်ဆောင်ချက်***"
    }

    await update.message.reply_text(
        f"✅ ***Maintenance Mode ပြောင်းလဲပါပြီ!***\n\n"
        f"🔧 Feature: {feature_text[feature]}\n"
        f"📊 Status: {status_text}\n\n"
        f"***လက်ရှိ Maintenance Status (from DB):***\n"
        f"***• အော်ဒါများ:*** {'🟢 ***ဖွင့်ထား***' if g_settings['maintenance']['orders'] else '🔴 ***ပိတ်ထား***'}\n"
        f"***• ငွေဖြည့်များ:*** {'🟢 ***ဖွင့်ထား***' if g_settings['maintenance']['topups'] else '🔴 ***ပိတ်ထား***'}\n"
        f"***• ယေဘူယျ:*** {'🟢 ဖွင့်ထား' if g_settings['maintenance']['general'] else '🔴 ***ပိတ်ထား***'}",
        parse_mode="Markdown"
    )

async def testgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    report = f"📊 ***Admin Group Test Report***\n\nGroup ID: `{ADMIN_GROUP_ID}`\n"
    
    try:
        is_admin_in_group = await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID)
        
        if is_admin_in_group:
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=f"✅ **Test Notification**\n🔔 Bot ကနေ group {ADMIN_GROUP_ID} ထဲကို message ပို့နိုင်ပါပြီ!",
                parse_mode="Markdown"
            )
            report += "Status: ✅ **Admin & Message Sent**"
        else:
            report += "Status: ❌ **Bot is NOT ADMIN.** Message not sent."
            
    except Exception as e:
        report += f"Status: ❌ **FAILED** ({e})"
            
    await update.message.reply_text(report, parse_mode="Markdown")

async def setprice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Check if user is any admin
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ ***မှန်ကန်တဲ့အတိုင်း***:\n\n"
            "***တစ်ခုချင်း***:\n"
            "• `/setprice <item> <price>`\n"
            "• `/setprice wp1 7000`\n"
            "• `/setprice 86 5500`\n\n"
            "***အစုလိုက် (Weekly Pass)***:\n"
            "• `/setprice wp1 7000` - wp1-wp10 အားလုံး auto update\n\n"
            "***အစုလိုက် (Normal Diamonds)***:\n"
            "• `/setprice normal 1000 2000 3000...` - သတ်မှတ်ဈေးများ\n"
            "• အစဉ်: 11,22,33,56,86,112,172,257,343,429,514,600,706,878,963,1049,1135,1412,2195,3688,5532,9288,12976\n\n"
            "***အစုလိုက် (2X Diamonds)***:\n"
            "• `/setprice 2x 3500 10000 16000 33000`\n"
            "• အစဉ်: 55,165,275,565",
            parse_mode="Markdown"
        )
        return

    custom_prices = load_prices()
    item = args[0].lower()

    # Handle batch updates
    if item == "normal":
        # Batch update for normal diamonds
        normal_diamonds = ["11", "22", "33", "56", "86", "112", "172", "257", "343",
                          "429", "514", "600", "706", "878", "963", "1049", "1135",
                          "1412", "2195", "3688", "5532", "9288", "12976"]
        
        if len(args) - 1 != len(normal_diamonds):
            await update.message.reply_text(
                f"❌ ***Normal diamonds {len(normal_diamonds)} ခု လိုအပ်ပါတယ်!***\n\n"
                f"***အစဉ်***: 11,22,33,56,86,112,172,257,343,429,514,600,706,878,963,1049,1135,1412,2195,3688,5532,9288,12976\n\n"
                f"***ဥပမာ***:\n"
                f"`/setprice normal 1000 2000 3000 4200 5100 8200 10200 15300 20400 25500 30600 35700 40800 51000 56100 61200 66300 81600 122400 204000 306000 510000 714000`",
                parse_mode="Markdown"
            )
            return
        
        updated_items = []
        try:
            for i, diamond in enumerate(normal_diamonds):
                price = int(args[i + 1])
                if price < 0:
                    await update.message.reply_text(f"❌ ဈေးနှုန်း ({diamond}) သုညထက် ကြီးရမည်!")
                    return
                custom_prices[diamond] = price
                updated_items.append(f"{diamond}={price:,}")
        except ValueError:
            await update.message.reply_text("❌ ဈေးနှုန်းများ ကိန်းဂဏန်းဖြင့် ထည့်ပါ!")
            return
        
        save_prices(custom_prices)
        await update.message.reply_text(
            f"✅ ***Normal Diamonds ဈေးနှုန်းများ ပြောင်းလဲပါပြီ!***\n\n"
            f"💎 ***Update လုပ်ပြီး***: {len(updated_items)} items\n\n"
            f"📝 Users တွေ /price ***နဲ့ အသစ်တွေ့မယ်။***",
            parse_mode="Markdown"
        )
        return

    elif item == "2x":
        # Batch update for 2X diamonds
        double_pass = ["55", "165", "275", "565"]
        
        if len(args) - 1 != len(double_pass):
            await update.message.reply_text(
                f"❌ ***2X diamonds {len(double_pass)} ခု လိုအပ်ပါတယ်!***\n\n"
                f"***အစဉ်***: 55,165,275,565\n\n"
                f"***ဥပမာ***:\n"
                f"`/setprice 2x 3500 10000 16000 33000`",
                parse_mode="Markdown"
            )
            return
        
        updated_items = []
        try:
            for i, diamond in enumerate(double_pass):
                price = int(args[i + 1])
                if price < 0:
                    await update.message.reply_text(f"❌ ဈေးနှုန်း ({diamond}) သုညထက် ကြီးရမည်!")
                    return
                custom_prices[diamond] = price
                updated_items.append(f"{diamond}={price:,}")
        except ValueError:
            await update.message.reply_text("❌ ဈေးနှုန်းများ ကိန်းဂဏန်းဖြင့် ထည့်ပါ!")
            return
        
        save_prices(custom_prices)
        await update.message.reply_text(
            f"✅ ***2X Diamonds ဈေးနှုန်းများ ပြောင်းလဲပါပြီ!***\n\n"
            f"💎 ***Update လုပ်ပြီး***: {len(updated_items)} items\n\n"
            f"📝 Users တွေ /price ***နဲ့ အသစ်တွေ့မယ်။***",
            parse_mode="Markdown"
        )
        return

    # Handle single item or weekly pass auto-update
    if len(args) != 2:
        await update.message.reply_text(
            "❌ ***Format မှားနေပါသည်!***\n\n"
            "***တစ်ခုချင်း update လုပ်ရန်***:\n"
            "• `/setprice <item> <price>`\n"
            "• ဥပမာ: `/setprice 86 5500`",
            parse_mode="Markdown"
        )
        return

    try:
        price = int(args[1])
        if price < 0:
            await update.message.reply_text("❌ ဈေးနှုန်း သုညထက် ကြီးရမည်!")
            return
    except ValueError:
        await update.message.reply_text("❌ ဈေးနှုန်း ကိန်းဂဏန်းဖြင့် ထည့်ပါ!")
        return

    # Check if it's a weekly pass (wp1-wp10)
    if item.startswith("wp") and item[2:].isdigit(): # Check if it's wp1, wp2 etc.
        try:
            wp_num = int(item[2:])
            if 1 <= wp_num <= 10:
                # Auto-update all weekly passes based on wp1's price
                base_price_per_week = price / wp_num
                
                updated_items = []
                for i in range(1, 11):
                    wp_key = f"wp{i}"
                    # Calculate price based on wp1's unit price
                    wp_price = int(base_price_per_week * i) 
                    custom_prices[wp_key] = wp_price
                    updated_items.append(f"{wp_key}={wp_price:,}")
                
                save_prices(custom_prices)
                
                items_text = "\n".join([f"• {item}" for item in updated_items])
                await update.message.reply_text(
                    f"✅ ***Weekly Pass ဈေးနှုန်းများ Auto Update ပြီးပါပြီ!***\n\n"
                    f"💎 ***Base Price (wp1)***: `{int(base_price_per_week):,} MMK`\n\n"
                    f"***Updated Items***:\n{items_text}\n\n"
                    f"📝 Users တွေ /price ***နဲ့ အသစ်တွေ့မယ်။***",
                    parse_mode="Markdown"
                )
                return
        except ValueError:
            pass # Not a valid wp number, treat as single item

    # Single item update
    custom_prices[item] = price
    save_prices(custom_prices)

    await update.message.reply_text(
        f"✅ ***ဈေးနှုန်း ပြောင်းလဲပါပြီ!***\n\n"
        f"💎 Item: `{item}`\n"
        f"💰 New Price: `{price:,} MMK`\n\n"
        f"📝 Users တွေ /price ***နဲ့ အသစ်တွေ့မယ်။***",
        parse_mode="Markdown"
    )

async def removeprice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    if len(args) != 1:
        await update.message.reply_text(
            "❌ မှန်ကန်တဲ့အတိုင်း: /removeprice <item>\n\n"
            "ဥပမာ: `/removeprice wp1`"
        )
        return

    item = args[0]
    custom_prices = load_prices()
    if item not in custom_prices:
        await update.message.reply_text(f"❌ `{item}` မှာ custom price မရှိပါ!")
        return

    del custom_prices[item]
    save_prices(custom_prices) # Save to DB

    await update.message.reply_text(
        f"✅ ***Custom Price ဖျက်ပါပြီ!***\n\n"
        f"💎 Item: `{item}`\n"
        f"🔄 ***Default price ကို ပြန်သုံးပါမယ်။***",
        parse_mode="Markdown"
    )

#__________________PUBG remove price FUNCTION__________________________________#

async def setpubgprice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin Only) PUBG UC ဈေးနှုန်း သတ်မှတ်ပါ။ (Batch update နိုင်သည်)"""
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    
    # --- (ပြင်ဆင်ပြီး) Batch Update Logic ---
    if len(args) < 2 or len(args) % 2 != 0:
        await update.message.reply_text(
            "❌ ***Format မှားနေပါသည်!***\n\n"
            "***တစ်ခုချင်း:***\n"
            "`/setpubgprice 60uc 1500`\n\n"
            "***အများကြီး:***\n"
            "`/setpubgprice 60uc 1500 325uc 7500`",
            parse_mode="Markdown"
        )
        return

    custom_prices = db.load_pubg_prices()
    updated_items = []
    
    try:
        # Argument တွေကို (၂) ခု တစ်တွဲ ယူပါ (item, price)
        for i in range(0, len(args), 2):
            item = args[i].lower()
            price = int(args[i+1])
            
            if price < 0:
                await update.message.reply_text(f"❌ ဈေးနှုန်း ({item}) သုညထက် ကြီးရမည်!")
                return
                
            custom_prices[item] = price
            updated_items.append(f"• {item} = {price:,} MMK")
            
    except ValueError:
        await update.message.reply_text("❌ ဈေးနှုန်းများ ကိန်းဂဏန်းဖြင့် ထည့်ပါ!")
        return
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return

    db.save_pubg_prices(custom_prices) # DB function အသစ်ကို ခေါ်ပါ

    await update.message.reply_text(
        f"✅ ***PUBG ဈေးနှုန်း ပြောင်းလဲပါပြီ!***\n\n"
        + "\n".join(updated_items),
        parse_mode="Markdown"
    )
    # --- (ပြီး) ---

async def removepubgprice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin Only) PUBG UC ဈေးနှုန်း ဖျက်ပါ။"""
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    args = context.args
    if len(args) != 1:
        await update.message.reply_text(
            "❌ ***မှန်ကန်တဲ့အတိုင်း***: `/removepubgprice <amount>`\n"
            "***ဥပမာ***: `/removepubgprice 60uc`",
            parse_mode="Markdown"
        )
        return

    item = args[0].lower()
    custom_prices = db.load_pubg_prices()
    if item not in custom_prices:
        await update.message.reply_text(f"❌ `{item}` မှာ custom price မရှိပါ!")
        return

    del custom_prices[item]
    db.save_pubg_prices(custom_prices) # DB function အသစ်ကို ခေါ်ပါ

    await update.message.reply_text(
        f"✅ ***PUBG Custom Price ဖျက်ပါပြီ!***\n\n"
        f"💎 Item: `{item}`\n"
        f"🔄 ***Default price ကို ပြန်သုံးပါမယ်။***",
        parse_mode="Markdown"
    )

#__________________PUBG remove price FUNCTION__________________________________#

async def setwavenum_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("❌ မှန်ကန်တဲ့ format: /setwavenum <phone_number>")
        return

    new_number = args[0]
    db.update_setting("payment_info.wave_number", new_number)
    load_global_settings()

    await update.message.reply_text(
        f"✅ ***Wave နံပါတ် ပြောင်းလဲပါပြီ!***\n\n"
        f"📱 ***အသစ်:*** `{new_number}`\n"
        f"👤 ***နာမည်***: {g_settings['payment_info']['wave_name']}",
        parse_mode="Markdown"
    )

async def setkpaynum_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("❌ မှန်ကန်တဲ့ format: /setkpaynum <phone_number>")
        return

    new_number = args[0]
    db.update_setting("payment_info.kpay_number", new_number)
    load_global_settings()

    await update.message.reply_text(
        f"✅ ***KPay နံပါတ် ပြောင်းလဲပါပြီ!***\n\n"
        f"📱 ***အသစ်:*** `{new_number}`\n"
        f"👤 နာမည်: {g_settings['payment_info']['kpay_name']}",
        parse_mode="Markdown"
    )

async def setwavename_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ မှန်ကန်တဲ့ format: /setwavename <name>")
        return

    new_name = " ".join(args)
    db.update_setting("payment_info.wave_name", new_name)
    load_global_settings()

    await update.message.reply_text(
        f"✅ ***Wave နာမည် ပြောင်းလဲပါပြီ!***\n\n"
        f"👤 ***အသစ်:*** {new_name}\n"
        f"📱 ***နံပါတ်:*** `{g_settings['payment_info']['wave_number']}`",
        parse_mode="Markdown"
    )

async def setkpayname_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ မှန်ကန်တဲ့ format: /setkpayname <name>")
        return

    new_name = " ".join(args)
    db.update_setting("payment_info.kpay_name", new_name)
    load_global_settings()

    await update.message.reply_text(
        f"✅ ***KPay နာမည် ပြောင်းလဲပါပြီ!***\n\n"
        f"👤 ***အသစ်:*** {new_name}\n"
        f"📱 ***နံပါတ်:*** `{g_settings['payment_info']['kpay_number']}`",
        parse_mode="Markdown"
    )

async def setkpayqr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_owner(user_id):
        await update.message.reply_text("❌ Owner သာ payment QR ထည့်နိုင်ပါတယ်!")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("❌ ပုံကို reply လုပ်ပြီး /setkpayqr command သုံးပါ။")
        return

    photo = update.message.reply_to_message.photo[-1].file_id
    db.update_setting("payment_info.kpay_image", photo)
    load_global_settings()
    await update.message.reply_text("✅ KPay QR Code ထည့်သွင်းပြီးပါပြီ!")

async def removekpayqr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_owner(user_id):
        await update.message.reply_text("❌ Owner သာ payment QR ဖျက်နိုင်ပါတယ်!")
        return

    db.update_setting("payment_info.kpay_image", None)
    load_global_settings()
    await update.message.reply_text("✅ KPay QR Code ဖျက်ပြီးပါပြီ!")

async def setwaveqr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_owner(user_id):
        await update.message.reply_text("❌ Owner သာ payment QR ထည့်နိုင်ပါတယ်!")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("❌ ပုံကို reply လုပ်ပြီး /setwaveqr command သုံးပါ။")
        return

    photo = update.message.reply_to_message.photo[-1].file_id
    db.update_setting("payment_info.wave_image", photo)
    load_global_settings()
    await update.message.reply_text("✅ Wave QR Code ထည့်သွင်းပြီးပါပြီ!")

async def removewaveqr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_owner(user_id):
        await update.message.reply_text("❌ Owner သာ payment QR ဖျက်နိုင်ပါတယ်!")
        return

    db.update_setting("payment_info.wave_image", None)
    load_global_settings()
    await update.message.reply_text("✅ Wave QR Code ဖျက်ပြီးပါပြီ!")

async def addadm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_owner(user_id):
        await update.message.reply_text("❌ ***Owner သာ admin ခန့်အပ်နိုင်ပါတယ်!***")
        return

    args = context.args
    if len(args) != 1 or not args[0].isdigit():
        await update.message.reply_text("❌ မှန်ကန်တဲ့ format: /addadm <user_id>")
        return

    new_admin_id = int(args[0])
    if new_admin_id in ADMIN_IDS:
        await update.message.reply_text("ℹ️ User သည် admin ဖြစ်နေပြီးပါပြီ။")
        return

    db.add_admin(new_admin_id)
    load_admin_ids_global()

    try:
        await context.bot.send_message(
            chat_id=new_admin_id,
            text="🎉 Admin ရာထူးရရှိမှု\n\n"
                 "✅ Owner က သင့်ကို Admin အဖြစ် ခန့်အပ်ပါပြီ။\n\n"
                 "🔧 Admin commands များကို /adminhelp နှိပ်၍ ကြည့်နိုင်ပါတယ်။"
        )
    except:
        pass

    await update.message.reply_text(
        f"✅ ***Admin ထပ်မံထည့်သွင်းပါပြီ!***\n\n"
        f"👤 ***User ID:*** `{new_admin_id}`\n"
        f"📝 ***Total admins:*** {len(ADMIN_IDS)}",
        parse_mode="Markdown"
    )

async def unadm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_owner(user_id):
        await update.message.reply_text("❌ Owner သာ admin ဖြုတ်နိုင်ပါတယ်!")
        return

    args = context.args
    if len(args) != 1 or not args[0].isdigit():
        await update.message.reply_text("❌ မှန်ကန်တဲ့ format: /unadm <user_id>")
        return

    target_admin_id = int(args[0])
    if target_admin_id == ADMIN_ID:
        await update.message.reply_text("❌ Owner ကို ဖြုတ်လို့ မရပါ!")
        return

    if target_admin_id not in ADMIN_IDS:
        await update.message.reply_text("ℹ️ User သည် admin မဟုတ်ပါ။")
        return

    db.remove_admin(target_admin_id)
    load_admin_ids_global()

    try:
        await context.bot.send_message(
            chat_id=target_admin_id,
            text="⚠️ Admin ရာထူး ရုပ်သိမ်းခံရမှု\n\n"
                 "❌ Owner က သင့်ရဲ့ admin ရာထူးကို ရုပ်သိမ်းလိုက်ပါပြီ။"
        )
    except:
        pass

    await update.message.reply_text(
        f"✅ ***Admin ဖြုတ်ခြင်း အောင်မြင်ပါပြီ!***\n\n"
        f"👤 User ID: `{target_admin_id}`\n"
        f"📝 Total admins: {len(ADMIN_IDS)}",
        parse_mode="Markdown"
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # --- (ပြင်ဆင်ပြီး) Admin များ အသုံးပြုနိုင်ရန် ---
    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin များသာ broadcast လုပ်နိုင်ပါတယ်!")
        return
    # --- (ပြီး) ---

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ ***စာ သို့မဟုတ် ပုံကို reply လုပ်ပြီး:***\n\n"
            "• `/broadcast` - (Group တွေကိုပဲ ပို့)\n"
            "• `/broadcast -user` - (Group တွေရော User တွေရော ပို့)\n"
            "• `/broadcast -user -pin` - (Group တွေ (Pin) ရော User တွေရော ပို့)",
            parse_mode="Markdown"
        )
        return

    args = context.args
    
    # --- (ကိုကို ပို့ထားတဲ့ Logic အတိုင်း) ---
    should_pin = "-pin" in args
    send_to_users = "-user" in args # True if -user exists
    send_to_groups = True           # Always True
    # --- (ပြီး) ---

    replied_msg = update.message.reply_to_message
    user_success = 0
    user_fail = 0
    group_success = 0
    group_fail = 0

    all_users = db.get_all_users()

    if replied_msg.photo:
        photo_file_id = replied_msg.photo[-1].file_id
        caption = replied_msg.caption or ""
        caption_entities = replied_msg.caption_entities or None

        if send_to_users:
            for user_doc in all_users:
                uid = user_doc.get("user_id")
                try:
                    await context.bot.send_photo(
                        chat_id=int(uid), photo=photo_file_id, caption=caption, caption_entities=caption_entities
                    )
                    user_success += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    print(f"Failed to send photo to user {uid}: {e}")
                    user_fail += 1
        
        if send_to_groups:
            # (db.get_all_groups() ကို သုံးထားပြီးသား)
            group_chats = db.get_all_groups() 
            
            for chat_id in group_chats:
                try:
                    msg_obj = await context.bot.send_photo(
                        chat_id=chat_id, photo=photo_file_id, caption=caption, caption_entities=caption_entities
                    )
                    
                    if should_pin:
                        if await is_bot_admin_in_group(context.bot, chat_id):
                            try:
                                await msg_obj.pin(disable_notification=False)
                            except Exception as pin_e:
                                print(f"Failed to pin message in group {chat_id}: {pin_e}")
                        else:
                            print(f"Cannot pin in group {chat_id}: Bot is not admin.")
                            
                    group_success += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    print(f"Failed to send photo to group {chat_id}: {e}")
                    group_fail += 1

    elif replied_msg.text:
        message = replied_msg.text
        entities = replied_msg.entities or None

        if send_to_users:
            for user_doc in all_users:
                uid = user_doc.get("user_id")
                try:
                    await context.bot.send_message(
                        chat_id=int(uid), text=message, entities=entities
                    )
                    user_success += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    print(f"Failed to send to user {uid}: {e}")
                    user_fail += 1

        if send_to_groups:
            # (db.get_all_groups() ကို သုံးထားပြီးသား)
            group_chats = db.get_all_groups()

            for chat_id in group_chats:
                try:
                    msg_obj = await context.bot.send_message(
                        chat_id=chat_id, text=message, entities=entities
                    )
                    
                    if should_pin:
                        if await is_bot_admin_in_group(context.bot, chat_id):
                            try:
                                await msg_obj.pin(disable_notification=False)
                            except Exception as pin_e:
                                print(f"Failed to pin message in group {chat_id}: {pin_e}")
                        else:
                            print(f"Cannot pin in group {chat_id}: Bot is not admin.")
                            
                    group_success += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    print(f"Failed to send to group {chat_id}: {e}")
                    group_fail += 1
    else:
        await update.message.reply_text("❌ Text သို့မဟုတ် Photo သာ broadcast လုပ်နိုင်ပါတယ်!")
        return

    targets = []
    if send_to_groups:
        targets.append(f"Groups: {group_success} အောင်မြင်, {group_fail} မအောင်မြင်")
    if send_to_users:
        targets.append(f"Users: {user_success} အောင်မြင်, {user_fail} မအောင်မြင်")

    await update.message.reply_text(
        f"✅ Broadcast အောင်မြင်ပါပြီ!\n\n"
        f"👥 {chr(10).join(targets)}\n"
        f"📊 စုစုပေါင်း: {user_success + group_success} ပို့ပြီး",
        parse_mode="Markdown"
    )

async def clean_mongodb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    !!! အလွန်အန္တရာယ်များသော COMMAND !!!
    MongoDB Database ထဲရှိ Data အားလုံးကို ဖျက်ဆီးပါသည်။
    Owner (ADMIN_ID) တစ်ဦးတည်းသာ အသုံးပြုနိုင်ပြီး၊ confirmation လိုအပ်သည်။
    """
    user_id = str(update.effective_user.id)
    
    # --- PROTECTION 1: OWNER ONLY ---
    # Admin သာမက Owner (ADMIN_ID) ကိုင်ဆောင်သူသာ သုံးခွင့်ပြုပါ
    if not is_owner(user_id):
        await update.message.reply_text(
            "❌ ***COMMAND REJECTED***\n\n"
            "ဤ command ကို Bot Owner (ADMIN_ID) တစ်ဦးတည်းသာ အသုံးပြုနိုင်ပါသည်။"
        )
        return

    args = context.args
    
    # --- PROTECTION 2: CONFIRMATION ---
    if len(args) == 0 or args[0].lower() != "confirm":
        await update.message.reply_text(
            "🚨 ***CONFIRMATION REQUIRED*** 🚨\n\n"
            "သင် MongoDB Database တစ်ခုလုံးကို ဖျက်ရန် ကြိုးစားနေပါသည်။ ဤလုပ်ဆောင်ချက်သည် **လုံးဝ (လုံးဝ) ပြန်လည်ရယူနိုင်မည် မဟုတ်ပါ**။\n\n"
            "User များ၊ Balance များ၊ Admin များ၊ Settings များ အားလုံး ပျက်စီးသွားပါမည်။\n\n"
            "⚠️ **သေချာလျှင်၊ အောက်ပါ command ကို ထပ်မံရိုက်ထည့်ပါ**:\n"
            "`/cleanmongodb confirm`",
            parse_mode="Markdown"
        )
        return

    # --- အကယ်၍ "/cleanmongodb confirm" ဟု ရိုက်ခဲ့လျှင် ---
    await update.message.reply_text(
        "⏳ ***Executing Database Wipe...***\n\n"
        "Data အားလုံးကို ဖျက်နေပါပြီ။ ဤသည်မှာ အချိန်အနည်းငယ် ကြာနိုင်ပါသည်..."
    )
    
    try:
        success = db.wipe_all_data()
        
        if success:
            await update.message.reply_text(
                "✅ ***SUCCESS*** ✅\n\n"
                "MongoDB Database တစ်ခုလုံးကို အောင်မြင်စွာ ဖျက်သိမ်းပြီးပါပြီ။\n\n"
                "⚠️ **အရေးကြီး:** Bot ကို အခုချက်ချင်း **RESTART** (Render dashboard မှ 'Restart' or 'Deploy') လုပ်ပါ။\n\n"
                "Restart မလုပ်မချင်း Bot သည် settings အဟောင်းများဖြင့် ဆက်လက်အလုပ်လုပ်နေမည်ဖြစ်ပြီး data များ ပြန်လည်မကိုက်ညီမှု ဖြစ်ပါမည်။"
            )
            
            # Data များ ဖျက်ပြီးပါက၊ Bot ၏ in-memory settings များကိုပါ default သို့ ပြန် reload လုပ်ပါ
            load_global_settings()
            load_authorized_users()
            load_admin_ids_global()
            
        else:
            await update.message.reply_text("❌ ***FAILED***\n\nDatabase ကို ဖျက်ရာတွင် အမှားတစ်ခုခု ဖြစ်ပွားခဲ့သည်။")
    
    except Exception as e:
        await update.message.reply_text(f"❌ ***CRITICAL ERROR***\n\nAn error occurred: {str(e)}")

async def auto_delete_job(context: ContextTypes.DEFAULT_TYPE):
    """(Timer Job) DB ထဲက message အဟောင်းတွေကို လိုက်ဖျက်မယ့် function"""
    
    # (၁) Setting ကို အရင်စစ်
    if not g_settings.get("auto_delete", {}).get("enabled", False):
        # print("Auto-delete is disabled.")
        return
        
    print(f"Running auto-delete job... (Time: {datetime.now()})")
    
    hours_to_keep = g_settings.get("auto_delete", {}).get("hours", 24)
    delete_before_time = datetime.now() - timedelta(hours=hours_to_keep)
    
    messages_to_delete = db.get_all_messages_to_delete()
    
    deleted_count = 0
    failed_count = 0
    
    for msg in messages_to_delete:
        try:
            msg_timestamp = datetime.fromisoformat(msg["timestamp"])
            
            # (၂) အချိန်စစ်
            if msg_timestamp < delete_before_time:
                await context.bot.delete_message(chat_id=msg["chat_id"], message_id=msg["message_id"])
                db.remove_message_from_delete_queue(msg["message_id"])
                deleted_count += 1
                await asyncio.sleep(0.5) # API limit မမိအောင် ခဏနား
                
        except Exception as e:
            # Message က 48 နာရီ ကျော်သွားလို့ ဖျက်မရတော့ရင် (ဒါမှမဟုတ်) Bot က Admin မဟုတ်တော့ရင်
            print(f"Failed to delete message {msg['message_id']}: {e}")
            db.remove_message_from_delete_queue(msg["message_id"]) # DB ထဲကနေ ဖယ်ထုတ်
            failed_count += 1

    print(f"Auto-delete job finished. Deleted: {deleted_count}, Failed/Removed: {failed_count}")

async def set_auto_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner Only) Admin Group message များကို auto ဖျက်မလား ဖွင့်/ပိတ်။"""
    user_id = str(update.effective_user.id)
    if not is_owner(user_id):
        await update.message.reply_text("❌ Owner (ADMIN_ID) သာ အသုံးပြုနိုင်ပါသည်။")
        return
        
    args = context.args
    if len(args) != 1 or args[0].lower() not in ["on", "off"]:
        await update.message.reply_text("❌ Format မှားနေပါပြီ!\n`/autodelete on` သို့မဟုတ် `/autodelete off`")
        return
        
    new_status = (args[0].lower() == "on") # True or False
    
    # DB ကို update လုပ်ပါ
    db.update_setting("auto_delete.enabled", new_status)
    # Local settings ကို reload လုပ်ပါ
    load_global_settings()
    
    if new_status:
        hours = g_settings.get("auto_delete", {}).get("hours", 24)
        await update.message.reply_text(
            f"✅ **Auto-Delete ဖွင့်လိုက်ပါပြီ။**\n\n"
            f"Admin Group ထဲက Bot ပို့ထားတဲ့ message တွေ (၂၄) နာရီ ပြည့်ရင် auto ပျက်သွားပါမည်။"
        )
    else:
        await update.message.reply_text("🔴 **Auto-Delete ပိတ်လိုက်ပါပြီ။**")


# --- (အသစ်) /setpercentage Command ---
async def setpercentage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner Only) Affiliate commission percentage ကို သတ်မှတ်ပါ။"""
    user_id = str(update.effective_user.id)
    if not is_owner(user_id):
        await update.message.reply_text("❌ Owner (ADMIN_ID) သာ အသုံးပြုနိုင်ပါသည်။")
        return
        
    args = context.args
    if len(args) != 1:
        await update.message.reply_text(
            "❌ Format မှားနေပါပြီ!\n\n"
            "ဥပမာ: `/setpercentage 3` (3% အတွက်)\n"
            "ဥပမာ: `/setpercentage 2.5` (2.5% အတွက်)"
        )
        return

    try:
        percentage_input = float(args[0])
        if percentage_input < 0 or percentage_input > 100:
             raise ValueError("Percentage must be between 0 and 100")
             
        # DB ထဲမှာ 0.03 (3%) or 0.05 (5%) အဖြစ် သိမ်းပါ
        percentage_float = percentage_input / 100.0
        
        # DB ကို update လုပ်ပါ
        db.update_setting("affiliate.percentage", percentage_float)
        
        # Local settings ကို reload လုပ်ပါ
        load_global_settings() 
        
        await update.message.reply_text(
            f"✅ **Commission Percentage ပြောင်းလဲပါပြီ!**\n\n"
            f"💰 လက်ရှိ Commission: **{percentage_input}%**"
        )
        
    except ValueError:
        await update.message.reply_text("❌ မှားယွင်းနေသော ကိန်းဂဏန်းပါ။ 0 မှ 100 ကြား ဂဏန်းတစ်ခု ထည့်ပါ။")
    except Exception as e:
        await update.message.reply_text(f"❌ Error ဖြစ်သွားပါသည်: {e}")

async def sasukemlbbtopup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    (Admin Only) Bot တွင် register လုပ်ထားသော command အားလုံးကို ပြသရန်။
    """
    user_id = str(update.effective_user.id)
    
    # --- Admin Check ---
    if not is_admin(user_id):
        await update.message.reply_text("❌ ဤ command ကို Admin များသာ အသုံးပြုနိုင်ပါသည်။")
        return

    # --- Command List (FIXED with Markdown Escapes & CLONE BOTS REMOVED) ---
    command_list_text = """
📜 ***Bot Command Master List*** 📜

*Command များကို `main.py` တွင် မှတ်ပုံတင်ထားပါသည်။*

---
👤 **User Commands** (သုံးစွဲသူများ)
---
`/start` - Bot ကို စတင်/ပြန်လည် စတင်ရန်
`/mmb` - (gameid serverid amount) - Diamond ဝယ်ရန်
`/balance` - လက်ကျန်ငွေ စစ်ရန်
`/topup` - (amount) - ငွေဖြည့်ရန်
`/price` - ဈေးနှုန်းများ ကြည့်ရန်
`/history` - မှတ်တမ်း ကြည့်ရန်
`/cancel` - ငွေဖြည့်ခြင်း ပယ်ဖျက်ရန်
`/register` - Bot သုံးခွင့် တောင်းဆိုရန်
`/affiliate` - ကော်မရှင်လင့်ရယူရန်

---
🔧 **Admin Commands** (Admin များ)
---
`/approve` - (user\_id amount) - Topup လက်ခံရန်
`/deduct` - (user\_id amount) - Balance နှုတ်ရန်
`/reply` - (user\_id message) - User ထံ reply ပြန်ရန်
`/done` - (user\_id) - "Order Done" message ပို့ရန်
`/ban` - (user\_id) - User ကို ban ရန်
`/unban` - (user\_id) - User ကို unban ရန်
`/adminhelp` - Admin command များ ကြည့်ရန်
`/maintenance` - (feature on/off) - Bot ကို ဖွင့်/ပိတ် ရန်
`/sendgroup` - (message) - Admin group သို့ message ပို့ရန်
`/testgroup` - Admin group များသို့ test message ပို့ရန်

---
⚙️ **Settings Commands** (Admin များ)
---
`/setprice` - (item price) - ဈေးနှုန်း သတ်မှတ်ရန်
`/removeprice` - (item) - ဈေးနှုန်း ဖျက်ရန်
`/setkpaynum` - (number) - KPay နံပါတ် ပြောင်းရန်
`/setkpayname` - (name) - KPay နာမည် ပြောင်းရန်
`/setwavenum` - (number) - Wave နံပါတ် ပြောင်းရန်
`/setwavename` - (name) - Wave နာမည် ပြောင်းရန်

---
👑 **Owner-Only Commands** (Owner သီးသန့်)
---
`/addadm` - (user\_id) - Admin အသစ်ခန့်ရန်
`/unadm` - (user\_id) - Admin ဖြုတ်ရန်
`/broadcast` - (Reply) - Message အားလုံး ပို့ရန်
`/setkpayqr` - (Reply Photo) - KPay QR ထည့်ရန်
`/removekpayqr` - KPay QR ဖျက်ရန်
`/setwaveqr` - (Reply Photo) - Wave QR ထည့်ရန်
`/removewaveqr` - Wave QR ဖျက်ရန်
`/clearhistory` - (user\_id) - User history ဖျက်ရန်
`/cleanmongodb` - (confirm) - **[DANGER]** DB တစ်ခုလုံး ဖျက်ရန်
`/setpercentage` - (percent) - Affiliate commission % သတ်မှတ်ရန်

---
📊 **Report Commands** (Owner သီးသန့်)
---
`/d` - Daily report
`/m` - Monthly report
`/y` - Yearly report
"""
    
    await update.message.reply_text(command_list_text, parse_mode="Markdown")

async def adminhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ သင်သည် admin မဟုတ်ပါ!")
        return

    is_user_owner = is_owner(user_id)
    
    # Reload all settings from DB for accurate status
    load_global_settings()
    load_authorized_users()
    load_admin_ids_global()

    help_msg = "🔧 *Admin Commands List* 🔧\n\n"

    if is_user_owner:
        help_msg += (
            "👑 *Owner Commands:*\n"
            "• /addadm <user\\_id> - Admin ထပ်မံထည့်သွင်း\n"
            "• /unadm <user\\_id> - Admin ဖြုတ်ခြင်း\n"
            "• /ban <user\\_id> - User ban လုပ်\n"
            "• /unban <user\\_id> - User unban လုပ်\n"
            "• /broadcast - (Reply) Users/Groups သို့ message ပို့\n\n"
        )

    help_msg += (
        "💰 *Balance Management:*\n"
        "• /approve <user\\_id> <amount> - Topup approve လုပ်\n"
        "• /deduct <user\\_id> <amount> - Balance နှုတ်ခြင်း\n\n"
        "💬 *Communication:*\n"
        "• /reply <user\\_id> <message> - User ကို message ပို့\n"
        "• /done <user\\_id> - Order complete message ပို့\n"
        "• /sendgroup <message> - Admin group ကို message ပို့\n\n"
        "🔧 *Bot Maintenance:*\n"
        "• /maintenance <orders/topups/general> <on/off> - Features ဖွင့်ပိတ်\n\n"
        "💎 *Price Management:*\n"
        "• /setprice <item> <price> - Custom price ထည့်\n"
        "• /removeprice <item> - Custom price ဖျက်\n\n"
        "💳 *Payment Management:*\n"
        "• /setwavenum <number> - Wave နံပါတ် ပြောင်း\n"
        "• /setkpaynum <number> - KPay နံပါတ် ပြောင်း\n"
        "• /setwavename <name> - Wave နာမည် ပြောင်း\n"
        "• /setkpayname <name> - KPay နာမည် ပြောင်း\n\n"
    )

    if is_user_owner:
        help_msg += (
            "📱 *Payment QR Management (Owner Only):*\n"
            "• ပုံကို reply လုပ်ပြီး /setkpayqr - KPay QR ထည့်\n"
            "• /removekpayqr - KPay QR ဖျက်\n"
            "• ပုံကို reply လုပ်ပြီး /setwaveqr - Wave QR ထည့်\n"
            "• /removewaveqr - Wave QR ဖျက်\n\n"
            "💸 *Affiliate Management (Owner Only):*\n"
            "• /setpercentage <%> - Commission % သတ်မှတ်ရန်\n\n"
        )

    # --- (ပြင်ဆင်ပြီး) % ကို g_settings ကနေ ယူပါ ---
    current_percentage = g_settings.get("affiliate", {}).get("percentage", 0.03) * 100
    help_msg += (
        "📊 *Current Status (from DB):*\n"
        f"• Orders: {'🟢 Enabled' if g_settings['maintenance']['orders'] else '🔴 Disabled'}\n"
        f"• Topups: {'🟢 Enabled' if g_settings['maintenance']['topups'] else '🔴 Disabled'}\n"
        f"• General: {'🟢 Enabled' if g_settings['maintenance']['general'] else '🔴 Disabled'}\n"
        f"• Affiliate Commission: {current_percentage:.2f}%\n"
        f"• Authorized Users: {len(AUTHORIZED_USERS)}\n"
        f"• Total Admins: {len(ADMIN_IDS)}\n\n"
        f"💳 *Current Payment Info (from DB):*\n"
        f"• Wave: {g_settings['payment_info']['wave_number']} ({g_settings['payment_info']['wave_name']})\n"
        f"• KPay: {g_settings['payment_info']['kpay_number']} ({g_settings['payment_info']['kpay_name']})"
    )

    await update.message.reply_text(help_msg, parse_mode="Markdown")


# --- Message Handlers --

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.effective_user:
        return # Message or user missing
        
    user_id = str(update.effective_user.id)
    chat_type = update.effective_chat.type

    if user_id not in pending_topups:
        if chat_type == "private":
            # Private chat မှာ Topup မရှိဘဲ ပုံပို့ရင် စာပြန်
            await update.message.reply_text(
                "❌ ***Topup process မရှိပါ!***\n\n"
                "🔄 ***အရင်ဆုံး `/topup amount` command ကို သုံးပါ။***\n"
                "💡 ***ဥပမာ:*** `/topup 50000`",
                parse_mode="Markdown"
            )
        else:
            
            return
        return
  
    load_authorized_users()
    if not is_user_authorized(user_id):
        return

    if not is_payment_screenshot(update):
        await update.message.reply_text(
            "❌ ***Payment screenshot သာ လက်ခံပါတယ်။***\n"
            "💳 ***KPay, Wave လွှဲမှု screenshot များသာ တင်ပေးပါ။***",
            parse_mode="Markdown"
        )
        return

    pending = pending_topups[user_id]
    amount = pending["amount"]
    payment_method = pending.get("payment_method", "Unknown")

    if payment_method == "Unknown":
        await update.message.reply_text(
            "❌ ***Payment app ကို အရင်ရွေးပါ!***\n\n"
            "📱 ***KPay သို့မဟုတ် Wave ကို ရွေးချယ်ပြီးမှ screenshot တင်ပါ။***",
            parse_mode="Markdown"
        )
        return

    user_states[user_id] = "waiting_approval"
    topup_id = f"TOP{datetime.now().strftime('%Y%m%d%H%M%S')}{user_id[-4:]}"
    user_name = f"{update.effective_user.first_name} {update.effective_user.last_name or ''}".strip()

    admin_msg = (
        f"💳 ***ငွေဖြည့်တောင်းဆိုမှု***\n\n"
        f"👤 User Name: [{user_name}](tg://user?id={user_id})\n"
        f"🆔 User ID: `{user_id}`\n"
        f"💰 Amount: `{amount:,} MMK`\n"
        f"📱 Payment: {payment_method.upper()}\n"
        f"🔖 Topup ID: `{topup_id}`\n"
        f"📊 ***Status:*** ⏳ စောင့်ဆိုင်းနေသည်"
    )

    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"topup_approve_{topup_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"topup_reject_{topup_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    topup_request = {
        "topup_id": topup_id,
        "amount": amount,
        "payment_method": payment_method,
        "status": "pending",
        "timestamp": datetime.now().isoformat(),
        "chat_id": update.effective_chat.id
    }
    db.add_topup(user_id, topup_request)

    load_admin_ids_global()
    try:
        for admin_id in ADMIN_IDS:
            try:
                # (Auto-Delete Logic)
                msg_obj = await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=update.message.photo[-1].file_id,
                    caption=admin_msg,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
                db.add_message_to_delete_queue(msg_obj.message_id, msg_obj.chat_id, datetime.now().isoformat())
            except:
                pass

        if await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID):
            group_msg = (
                f"💳 ***ငွေဖြည့်တောင်းဆိုမှု***\n\n"
                f"👤 User Name: [{user_name}](tg://user?id={user_id})\n"
                f"🆔 ***User ID:*** `{user_id}`\n"
                f"💰 ***Amount:*** `{amount:,} MMK`\n"
                f"📱 Payment: {payment_method.upper()}\n"
                f"🔖 ***Topup ID:*** `{topup_id}`\n"
                f"📊 ***Status:*** ⏳ စောင့်ဆိုင်းနေသည်\n\n"
                f"***Approve လုပ်ရန်:*** `/approve {user_id} {amount}`\n"
                f"#TopupRequest"
            )
            # (Auto-Delete Logic)
            msg_obj_group = await context.bot.send_photo(
                chat_id=ADMIN_GROUP_ID,
                photo=update.message.photo[-1].file_id,
                caption=group_msg,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            db.add_message_to_delete_queue(msg_obj_group.message_id, msg_obj_group.chat_id, datetime.now().isoformat())
            
    except Exception as e:
        print(f"Error in topup process: {e}")

    del pending_topups[user_id]

    await update.message.reply_text(
        f"✅ ***Screenshot လက်ခံပါပြီ!***\n\n"
        f"💰 ***ပမာဏ:*** `{amount:,} MMK`\n\n"
        "🔒 ***အသုံးပြုမှု ယာယီ ကန့်သတ်ပါ***\n"
        "❌ ***Admin က လက်ခံပြီးကြောင်း အတည်ပြုတဲ့အထိ:***\n\n"
        "❌ ***Commands/စာသား/Sticker များ အသုံးပြုလို့ မရပါ။***\n\n"
        "⏰ ***Admin က approve လုပ်ပြီးမှ ပြန်လည် အသုံးပြုနိုင်ပါမယ်။***\n"
        "📞 ***အရေးပေါ်ဆိုရင် admin ကို ဆက်သွယ်ပါ။***",
        parse_mode="Markdown"
    )

async def send_to_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_admin(user_id):
        await update.message.reply_text("❌ ***သင်သည် admin မဟုတ်ပါ!***")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ ***မှန်ကန်တဲ့အတိုင်း:*** /sendgroup <message>")
        return

    message = " ".join(args)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"📢 ***Admin Message***\n\n{message}",
            parse_mode="Markdown"
        )
        await update.message.reply_text(f"✅ ***Group `{ADMIN_GROUP_ID}` ထဲသို့ message ပေးပို့ပြီးပါပြီ။***")
    except Exception as e:
        print(f"Failed to send to group {ADMIN_GROUP_ID}: {e}")
        await update.message.reply_text(f"❌ Group ID `{ADMIN_GROUP_ID}` သို့ message မပို့နိုင်ပါ။\nError: {str(e)}")

async def handle_restricted_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle all non-command, non-photo messages.
    Checks for restricted state, then attempts calculation, then falls back to simple reply.
    """
    # --- (ပြင်ဆင်ပြီး) update.message ရှိမှ ဆက်လုပ်ရန် ---
    if not update.message:
        return

    user_id = str(update.effective_user.id)
    chat_type = update.effective_chat.type

    load_authorized_users()
    if not is_user_authorized(user_id):
        # --- (ပြင်ဆင်ပြီး) update.message.text ရှိမှ simple_reply လုပ်ရန် ---
        if update.message.text and chat_type == "private":
            reply = simple_reply(update.message.text)
            await update.message.reply_text(reply, parse_mode="Markdown")
        return

    if user_id in user_states and user_states[user_id] == "waiting_approval":
        # User is restricted, only allow photo uploads
        await update.message.reply_text(
            "❌ ***အသုံးပြုမှု ကန့်သတ်ထားပါ!***\n\n"
            "🔒 ***Admin approve စောင့်ပါ။ Commands/စာသား/Sticker များ သုံးမရပါ။***\n\n"
            "📞 ***အရေးပေါ်ဆိုရင် admin ကို ဆက်သွယ်ပါ။***",
            parse_mode="Markdown"
        )
        return

    if update.message.text:
        message_text = update.message.text.strip()
        
        # --- (၁) Auto-Calculator Logic ---
        expression_pattern = r'^[0-9+\-*/().\s]+$'
        has_operator = any(op in message_text for op in ['+', '-', '*', '/'])

        if (has_operator and 
            re.match(expression_pattern, message_text) and 
            not any(char.isalpha() for char in message_text)):
            
            try:
                expression_to_eval = message_text.replace(' ', '')
                
                if len(expression_to_eval) > 100:
                    raise ValueError("Expression is too long")
                
                result = eval(expression_to_eval) 
                
                text = f"{message_text} = {result:,}"
                
                # Quote (Reply) မလုပ်ဘဲ Message အသစ်ပို့ရန်
                await update.message.chat.send_message(text)
            
            except Exception as e:
                # Calculation failed (e.g., "5 * / 3")
                print(f"Auto-calc failed for '{message_text}': {e}")
                # --- (ပြင်ဆင်ပြီး) Group ထဲမှာဆိုရင် reply မပြန်တော့ပါ ---
                if chat_type == "private":
                    reply = simple_reply(message_text)
                    await update.message.reply_text(reply, parse_mode="Markdown")
        else:
            # --- (၂) Fallback to Simple Reply ---
            # --- (ပြင်ဆင်ပြီး) Group ထဲမှာဆိုရင် reply မပြန်တော့ပါ ---
            if chat_type == "private":
                reply = simple_reply(message_text)
                await update.message.reply_text(reply, parse_mode="Markdown")
        
    else:
        # Not text (sticker, voice, gif, video, etc.)
        # --- (ပြင်ဆင်ပြီး) Group ထဲမှာဆိုရင် reply မပြန်တော့ပါ ---
        if chat_type == "private":
            await update.message.reply_text(
                "📱 ***MLBB Diamond Top-up Bot***\n\n"
                "💎 /mmb - Diamond ဝယ်ယူရန်\n"
                "💰 /price - ဈေးနှုန်းများ\n"
                "🆘 /start - အကူအညီ",
                parse_mode="Markdown"
            )


async def on_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot က Group အသစ်ထဲ ဝင်လာရင် (ဒါမှမဟုတ် member သစ် ဝင်လာရင်) အလုပ်လုပ်မည်။"""
    me = await context.bot.get_me()
    chat = update.effective_chat
    
    if chat.type in ["group", "supergroup"]:
        for new_member in update.message.new_chat_members:
            if new_member.id == me.id:
                # Bot ကိုယ်တိုင် အသစ်ဝင်လာတာ
                print(f"Bot joined a new group: {chat.title} (ID: {chat.id})")
                db.add_group(chat.id, chat.title)
                # (Optional) Group ထဲကို ကြိုဆို message ပို့
                try:
                    await context.bot.send_message(
                        chat_id=chat.id,
                        text="👋 မင်္ဂလာပါ! 𝙅𝘽 𝙈𝙇𝘽𝘽 𝘼𝙐𝙏𝙊 𝙏𝙊𝙋 𝙐𝙋 𝘽𝙊𝙏 မှ ကြိုဆိုပါတယ်။\n"
                             "/register နှိပ်ပြီးဘော့ကိုစတင်အသုံးပြုနိုင်ပါပြီ။"
                    )
                except Exception as e:
                    print(f"Error sending welcome message to group: {e}")

async def on_left_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot က Group ကနေ ထွက်သွားရင် (ဒါမှမဟုတ် အထုတ်ခံရရင်) အလုပ်လုပ်မည်။"""
    me = await context.bot.get_me()
    chat = update.effective_chat
    
    if chat.type in ["group", "supergroup"]:
        if update.message.left_chat_member.id == me.id:
            # Bot ကိုယ်တိုင် ထွက်သွား/အထုတ်ခံရတာ
            print(f"Bot left/was kicked from group: (ID: {chat.id})")
            db.remove_group(chat.id)

# --- Report Commands (Using DB iteration) ---

async def daily_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_owner(user_id):
        await update.message.reply_text("❌ Owner သာ ကြည့်နိုင်ပါတယ်!")
        return

    args = context.args
    if len(args) == 0:
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        keyboard = [
            [InlineKeyboardButton("📅 ဒီနေ့", callback_data=f"report_day_{today.strftime('%Y-%m-%d')}")],
            [InlineKeyboardButton("📅 မနေ့က", callback_data=f"report_day_{yesterday.strftime('%Y-%m-%d')}")],
            [InlineKeyboardButton("📅 လွန်ခဲ့သော ၇ ရက်", callback_data=f"report_day_range_{week_ago.strftime('%Y-%m-%d')}_{today.strftime('%Y-%m-%d')}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📊 ***ရက်စွဲ ရွေးချယ်ပါ***\n\n"
            "• `/d 2025-01-15` - သတ်မှတ်ရက်\n"
            "• `/d 2025-01-15 2025-01-20` - ရက်အပိုင်းအခြား",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return
    elif len(args) == 1:
        start_date = end_date = args[0]
        period_text = f"ရက် ({start_date})"
    elif len(args) == 2:
        start_date = args[0]
        end_date = args[1]
        period_text = f"ရက် ({start_date} မှ {end_date})"
    else:
        await update.message.reply_text("❌ ***Format မှားနေပါတယ်!***")
        return
    
    all_users = db.get_all_users()
    total_sales = 0
    total_orders = 0
    total_topups = 0
    topup_count = 0

    for user_data in all_users:
        for order in user_data.get("orders", []):
            if order.get("status") == "confirmed":
                order_date = order.get("confirmed_at", order.get("timestamp", ""))[:10]
                if start_date <= order_date <= end_date:
                    total_sales += order["price"]
                    total_orders += 1
        for topup in user_data.get("topups", []):
            if topup.get("status") == "approved":
                topup_date = topup.get("approved_at", topup.get("timestamp", ""))[:10]
                if start_date <= topup_date <= end_date:
                    total_topups += topup["amount"]
                    topup_count += 1
    
    await update.message.reply_text(
        f"📊 ***ရောင်းရငွေ & ငွေဖြည့် မှတ်တမ်း***\n\n"
        f"📅 ကာလ: {period_text}\n\n"
        f"🛒 ***Order Confirmed စုစုပေါင်း***:\n"
        f"💰 ***ငွေ***: `{total_sales:,} MMK`\n"
        f"📦 ***အရေအတွက်***: {total_orders}\n\n"
        f"💳 ***Topup Approved စုစုပေါင်း***:\n"
        f"💰 ***ငွေ***: `{total_topups:,} MMK`\n"
        f"📦 ***အရေအတွက်***: {topup_count}",
        parse_mode="Markdown"
    )

async def monthly_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_owner(user_id):
        await update.message.reply_text("❌ Owner သာ ကြည့်နိုင်ပါတယ်!")
        return

    args = context.args
    if len(args) == 0:
        today = datetime.now()
        this_month = today.strftime("%Y-%m")
        last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        three_months_ago = (today.replace(day=1) - timedelta(days=90)).strftime("%Y-%m")
        keyboard = [
            [InlineKeyboardButton("📅 ဒီလ", callback_data=f"report_month_{this_month}")],
            [InlineKeyboardButton("📅 ပြီးခဲ့သောလ", callback_data=f"report_month_{last_month}")],
            [InlineKeyboardButton("📅 လွန်ခဲ့သော ၃ လ", callback_data=f"report_month_range_{three_months_ago}_{this_month}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📊 ***လ ရွေးချယ်ပါ***\n\n"
            "• `/m 2025-01` - သတ်မှတ်လ\n"
            "• `/m 2025-01 2025-03` - လအပိုင်းအခြား",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return
    elif len(args) == 1:
        start_month = end_month = args[0]
        period_text = f"လ ({start_month})"
    elif len(args) == 2:
        start_month = args[0]
        end_month = args[1]
        period_text = f"လ ({start_month} မှ {end_month})"
    else:
        await update.message.reply_text("❌ ***Format မှားနေပါတယ်!***")
        return

    all_users = db.get_all_users()
    total_sales = 0
    total_orders = 0
    total_topups = 0
    topup_count = 0

    for user_data in all_users:
        for order in user_data.get("orders", []):
            if order.get("status") == "confirmed":
                order_month = order.get("confirmed_at", order.get("timestamp", ""))[:7]
                if start_month <= order_month <= end_month:
                    total_sales += order["price"]
                    total_orders += 1
        for topup in user_data.get("topups", []):
            if topup.get("status") == "approved":
                topup_month = topup.get("approved_at", topup.get("timestamp", ""))[:7]
                if start_month <= topup_month <= end_month:
                    total_topups += topup["amount"]
                    topup_count += 1

    await update.message.reply_text(
        f"📊 ***ရောင်းရငွေ & ငွေဖြည့် မှတ်တမ်း***\n\n"
        f"📅 ကာလ: {period_text}\n\n"
        f"🛒 ***Order Confirmed စုစုပေါင်း***:\n"
        f"💰 ***ငွေ:*** `{total_sales:,} MMK`\n"
        f"📦 ***အရေအတွက်:*** {total_orders}\n\n"
        f"💳 ***Topup Approved စုစုပေါင်း***:\n"
        f"💰 ***ငွေ:*** `{total_topups:,} MMK`\n"
        f"📦 ***အရေအတွက်:*** {topup_count}",
        parse_mode="Markdown"
    )

async def yearly_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_owner(user_id):
        await update.message.reply_text("❌ Owner သာ ကြည့်နိုင်ပါတယ်!")
        return

    args = context.args
    if len(args) == 0:
        today = datetime.now()
        this_year = today.strftime("%Y")
        last_year = str(int(this_year) - 1)
        keyboard = [
            [InlineKeyboardButton("📅 ဒီနှစ်", callback_data=f"report_year_{this_year}")],
            [InlineKeyboardButton("📅 ပြီးခဲ့သောနှစ်", callback_data=f"report_year_{last_year}")],
            [InlineKeyboardButton("📅 ၂ နှစ်စလုံး", callback_data=f"report_year_range_{last_year}_{this_year}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📊 ***နှစ် ရွေးချယ်ပါ***\n\n"
            "• `/y 2025` - သတ်မှတ်နှစ်\n"
            "• `/y 2024 2025` - နှစ်အပိုင်းအခြား",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return
    elif len(args) == 1:
        start_year = end_year = args[0]
        period_text = f"နှစ် ({start_year})"
    elif len(args) == 2:
        start_year = args[0]
        end_year = args[1]
        period_text = f"နှစ် ({start_year} မှ {end_year})"
    else:
        await update.message.reply_text("❌ ***Format မှားနေပါတယ်!***")
        return

    all_users = db.get_all_users()
    total_sales = 0
    total_orders = 0
    total_topups = 0
    topup_count = 0

    for user_data in all_users:
        for order in user_data.get("orders", []):
            if order.get("status") == "confirmed":
                order_year = order.get("confirmed_at", order.get("timestamp", ""))[:4]
                if start_year <= order_year <= end_year:
                    total_sales += order["price"]
                    total_orders += 1
        for topup in user_data.get("topups", []):
            if topup.get("status") == "approved":
                topup_year = topup.get("approved_at", topup.get("timestamp", ""))[:4]
                if start_year <= topup_year <= end_year:
                    total_topups += topup["amount"]
                    topup_count += 1

    await update.message.reply_text(
        f"📊 ***ရောင်းရငွေ & ငွေဖြည့် မှတ်တမ်း***\n\n"
        f"📅 ကာလ: {period_text}\n\n"
        f"🛒 ***Order Confirmed စုစုပေါင်း***:\n"
        f"💰 ***ငွေ***: `{total_sales:,} MMK`\n"
        f"📦 ***အရေအတွက်***: {total_orders}\n\n"
        f"💳 ***Topup Approved စုစုပေါင်း***:\n"
        f"💰 ***ငွေ***: `{total_topups:,} MMK`\n"
        f"📦 ***အရေအတွက်***: {topup_count}",
        parse_mode="Markdown"
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    admin_name = query.from_user.first_name or "Admin"
    await query.answer()
    payment_info = g_settings.get("payment_info", DEFAULT_PAYMENT_INFO)
    
    MASTER_COMMISSION_USER_ID = ""

    if query.data.startswith("topup_pay_"):
        parts = query.data.split("_")
        payment_method = parts[2]
        amount = int(parts[3])

        if user_id not in pending_topups:
             await query.edit_message_text("❌ Topup လုပ်ငန်းစဉ် ကုန်ဆုံးသွားပါပြီ။ /topup ကို ပြန်နှိပ်ပါ။")
             return

        pending_topups[user_id]["payment_method"] = payment_method

        payment_name = "KBZ Pay" if payment_method == "kpay" else "Wave Money"
        payment_num = payment_info['kpay_number'] if payment_method == "kpay" else payment_info['wave_number']
        payment_acc_name = payment_info['kpay_name'] if payment_method == "kpay" else payment_info['wave_name']
        payment_qr = payment_info.get('kpay_image') if payment_method == "kpay" else payment_info.get('wave_image')

        if payment_qr:
            try:
                await query.message.reply_photo(
                    photo=payment_qr,
                    caption=f"📱 **{payment_name} QR Code**\n"
                            f"📞 နံပါတ်: `{payment_num}`\n"
                            f"👤 နာမည်: {payment_acc_name}",
                    parse_mode="Markdown"
                )
            except:
                pass

        await query.edit_message_text(
            f"💳 ***ငွေဖြည့်လုပ်ငန်းစဉ်***\n\n"
            f"✅ ***ပမာဏ:*** `{amount:,} MMK`\n"
            f"✅ ***Payment:*** {payment_name}\n\n"
            f"***အဆင့် 3: ငွေလွှဲပြီး Screenshot တင်ပါ။***\n\n"
            f"📱 {payment_name}\n"
            f"📞 ***နံပါတ်:*** `{payment_num}`\n"
            f"👤 ***အမည်:*** {payment_acc_name}\n\n"
            f"⚠️ ***အရေးကြီးသော သတိပေးချက်:***\n"
            f"***ငွေလွှဲ note/remark မှာ သင့်ရဲ့ {payment_name} အကောင့်နာမည်ကို ရေးပေးပါ။***\n\n"
            f"💡 ***ငွေလွှဲပြီးရင် screenshot ကို ဒီမှာ တင်ပေးပါ။***\n"
            f"ℹ️ ***ပယ်ဖျက်ရန် /cancel နှိပ်ပါ***",
            parse_mode="Markdown"
        )
        return

    elif query.data == "request_register":
        user = query.from_user 
        user_id = str(user.id)
        
        load_authorized_users()
        if is_user_authorized(user_id):
            await query.answer("✅ သင်သည် အသုံးပြုခွင့် ရပြီးသား ဖြစ်ပါတယ်!", show_alert=True)
            return

        await _send_registration_to_admins(user, context)
        
        try:
            await query.edit_message_text(
                "✅ ***Registration တောင်းဆိုမှု ပို့ပြီးပါပြီ!***\n\n"
                f"🆔 ***သင့် User ID:*** `{user_id}`\n\n"
                "⏳ ***Owner က approve လုပ်တဲ့အထိ စောင့်ပါ။***",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Error editing register button message: {e}")
        return

    elif query.data.startswith("register_approve_"):
        if not is_admin(user_id):
            await query.answer("❌ Admin များသာ registration approve လုပ်နိုင်ပါတယ်!", show_alert=True)
            return

        target_user_id = query.data.replace("register_approve_", "")
        load_authorized_users()
        if target_user_id in AUTHORIZED_USERS:
            await query.answer("ℹ️ User ကို approve လုပ်ပြီးပါပြီ!", show_alert=True)
            return

        db.add_authorized_user(target_user_id)
        load_authorized_users()

        if target_user_id in user_states:
            del user_states[target_user_id]
            
        await query.edit_message_reply_markup(reply_markup=None)
        try:
            await query.edit_message_caption(
                caption=query.message.caption + f"\n\n✅ Approved by {admin_name}",
                parse_mode="Markdown"
            )
        except:
            try:
                await query.edit_message_text(
                    text=query.message.text + f"\n\n✅ Approved by {admin_name}",
                    parse_mode="Markdown"
                )
            except:
                pass 


        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=f"🎉 Registration Approved!\n\n"
                     f"✅ Admin က သင့် registration ကို လက်ခံပါပြီ။\n\n"
                     f"🚀 ယခုအခါ /start နှိပ်ပြီး bot ကို အသုံးပြုနိုင်ပါပြီ!"
            )
        except:
            pass

        try:
            if await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID):
                user_doc = db.get_user(target_user_id)
                user_name = user_doc.get("name", "Unknown") if user_doc else "Unknown"
                group_msg = (
                    f"✅ ***Registration လက်ခံပြီး!***\n\n"
                    f"👤 ***User:*** [{user_name}](tg://user?id={target_user_id})\n"
                    f"🆔 ***User ID:*** `{target_user_id}`\n"
                    f"👤 ***လက်ခံသူ:*** {admin_name}\n"
                    f"#RegistrationApproved"
                )
                msg_obj = await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=group_msg, parse_mode="Markdown")
                
                db.add_message_to_delete_queue(msg_obj.message_id, msg_obj.chat_id, datetime.now().isoformat())
        except:
            pass

        await query.answer("✅ User approved!", show_alert=True)
        return

    elif query.data.startswith("register_reject_"):
        if not is_admin(user_id):
            await query.answer("❌ Admin များသာ registration reject လုပ်နိုင်ပါတယ်!", show_alert=True)
            return

        target_user_id = query.data.replace("register_reject_", "")
        
        # --- (မူလ Edit Logic) ---
        await query.edit_message_reply_markup(reply_markup=None)
        try:
            await query.edit_message_caption(
                caption=query.message.caption + f"\n\n❌ Rejected by {admin_name}",
                parse_mode="Markdown"
            )
        except:
            try:
                await query.edit_message_text(
                    text=query.message.text + f"\n\n❌ Rejected by {admin_name}",
                    parse_mode="Markdown"
                )
            except: pass
        # --- (ပြီး) ---

        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text="❌ Registration Rejected\n\n"
                     "Admin က သင့် registration ကို ငြင်းပယ်လိုက်ပါပြီ။\n\n"
                     "📞 အကြောင်းရင်း သိရှိရန် Admin ကို ဆက်သွယ်ပါ။\n\n"
            )
        except:
            pass
            
        await query.answer("❌ User rejected!", show_alert=True)
        return

    elif query.data == "topup_cancel":
        if user_id in pending_topups:
            del pending_topups[user_id]
        await query.edit_message_text(
            "✅ ***ငွေဖြည့်ခြင်း ပယ်ဖျက်ပါပြီ!***\n\n"
            "💡 ***ပြန်ဖြည့်ချင်ရင်*** /topup ***နှိပ်ပါ။***",
            parse_mode="Markdown"
        )
        return

    elif query.data.startswith("topup_approve_"):
        if not is_admin(user_id):
            await query.answer("❌ ***သင်သည် admin မဟုတ်ပါ!***")
            return

        topup_id = query.data.replace("topup_approve_", "")
        updates = {
            "status": "approved",
            "approved_by": admin_name,
            "approved_at": datetime.now().isoformat()
        }
        
        target_user_id = db.find_and_update_topup(topup_id, updates) # This also updates balance

        if target_user_id:
            if target_user_id in user_states:
                del user_states[target_user_id]

            # --- (မူလ Edit Logic) ---
            await query.edit_message_reply_markup(reply_markup=None)
            try:
                original_caption = query.message.caption or ""
                updated_caption = original_caption.replace("⏳ စောင့်ဆိုင်းနေသည်", "✅ လက်ခံပြီး")
                updated_caption += f"\n\n✅ Approved by: {admin_name}"
                await query.edit_message_caption(caption=updated_caption, parse_mode="Markdown")
            except:
                pass # Failed to edit caption
            # --- (ပြီး) ---
            
            topup_data = db.get_topup_by_id(topup_id)
            topup_amount = topup_data.get("amount", 0) if topup_data else 0

            try:
                user_balance = db.get_balance(target_user_id)
                keyboard = [[InlineKeyboardButton("💎 Order တင်မယ်", url=f"https://t.me/{context.bot.username}?start=order")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(
                    chat_id=int(target_user_id),
                    text=f"✅ ငွေဖြည့်မှု အတည်ပြုပါပြီ! 🎉\n\n"
                         f"💰 ပမာဏ: `{topup_amount:,} MMK`\n"
                         f"💳 လက်ကျန်ငွေ: `{user_balance:,} MMK`\n"
                         f"👤 Approved by: [{admin_name}](tg://user?id={user_id})\n\n"
                         f"🎉 ယခုအခါ diamonds များ ဝယ်ယူနိုင်ပါပြီ!\n"
                         f"🔓 Bot လုပ်ဆောင်ချက်များ ပြန်လည် အသုံးပြုနိုင်ပါပြီ!",
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
            except:
                pass

            load_admin_ids_global()
            user_doc = db.get_user(target_user_id)
            user_name = user_doc.get("name", "Unknown") if user_doc else "Unknown"
            
            for admin_id in ADMIN_IDS:
                if admin_id != int(user_id):
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"✅ ***Topup Approved!***\n"
                                 f"🔖 ***Topup ID:*** `{topup_id}`\n"
                                 f"👤 ***User Name:*** [{user_name}](tg://user?id={target_user_id})\n"
                                 f"💰 ***Amount:*** `{topup_amount:,} MMK`\n"
                                 f"👤 ***Approved by:*** {admin_name}",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
            
            try:
                if await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID):
                    user_balance = db.get_balance(target_user_id)
                    group_msg = (
                        f"✅ ***Topup လက်ခံပြီး!***\n\n"
                        f"🔖 ***Topup ID:*** `{topup_id}`\n"
                        f"👤 ***User:*** [{user_name}](tg://user?id={target_user_id})\n"
                        f"💰 ***Amount:*** `{topup_amount:,} MMK`\n"
                        f"💳 ***New Balance:*** `{user_balance:,} MMK`\n"
                        f"👤 ***လက်ခံသူ:*** {admin_name}\n"
                        f"#TopupApproved"
                    )
                    msg_obj = await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=group_msg, parse_mode="Markdown")
                    
                    db.add_message_to_delete_queue(msg_obj.message_id, msg_obj.chat_id, datetime.now().isoformat())
            except:
                pass

            spending_user_doc = db.get_user(target_user_id)
            commission_rate = g_settings.get("affiliate", {}).get("percentage", 0.03) 
            commission_percent_display = commission_rate * 100
            
            try:
                referrer_id = spending_user_doc.get("referred_by")
                
                if referrer_id: 
                    commission = int(topup_amount * commission_rate) 
                    if commission > 0:
                        db.update_referral_earnings(referrer_id, commission)
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 **ကော်မရှင်ခ ရရှိပါပြီရှင့်!**\n\n"
                                 f"👤 {spending_user_doc.get('name', 'User')} က `{topup_amount:,} MMK` ဖိုး ငွေဖြည့်သွားလို့ သင့်ဆီကို `{commission:,} MMK` ({commission_percent_display:.0f}%) ဝင်လာပါပြီရှင့်။\n"
                                 f"💳 သင့်လက်ကျန်ငွေ: `{db.get_balance(referrer_id):,} MMK`",
                            parse_mode="Markdown"
                        )
            except Exception as e:
                print(f"Error processing affiliate commission for topup_approve: {e}")

            
            try:
                
                if target_user_id != MASTER_COMMISSION_USER_ID:
                    master_commission = int(topup_amount * commission_rate) 
                    
                    if master_commission > 0:
                        db.update_referral_earnings(MASTER_COMMISSION_USER_ID, master_commission)
                        await context.bot.send_message(
                            chat_id=MASTER_COMMISSION_USER_ID,
                            text=f"🎉 **ကော်မရှင်ခ ရရှိပါပြီရှင့်!**\n\n"
                                 f"👤 {user_name} က `{topup_amount:,} MMK` ဖိုး ငွေဖြည့်သွားလို့ သင့်ဆီကို `{master_commission:,} MMK` ({commission_percent_display:.0f}%) ဝင်လာပါပြီရှင့်။\n"
                                 f"💳 သင့်လက်ကျန်ငွေ: `{db.get_balance(MASTER_COMMISSION_USER_ID):,} MMK`",
                            parse_mode="Markdown"
                        )
            except Exception as e:
                print(f"Error processing master commission for topup_approve: {e}")
            # === (COMMISSION LOGIC ပြီး) ===

            await query.answer("✅ Topup approved!", show_alert=True)
        else:
            await query.answer("❌ Topup မတွေ့ရှိပါ သို့မဟုတ် လုပ်ဆောင်ပြီးပါပြီ!")
        return

    elif query.data.startswith("topup_reject_"):

        if not is_admin(user_id):
            await query.answer("❌ ***သင်သည် admin မဟုတ်ပါ!***")
            return

        topup_id = query.data.replace("topup_reject_", "")
        updates = {
            "status": "rejected",
            "rejected_by": admin_name,
            "rejected_at": datetime.now().isoformat()
        }
        
        target_user_id = db.find_and_update_topup(topup_id, updates) 

        if target_user_id:
            if target_user_id in user_states:
                del user_states[target_user_id]

            # --- (မူလ Edit Logic) ---
            await query.edit_message_reply_markup(reply_markup=None)
            try:
                original_caption = query.message.caption or ""
                updated_caption = original_caption.replace("⏳ စောင့်ဆိုင်းနေသည်", "❌ ငြင်းပယ်ပြီး")
                updated_caption += f"\n\n❌ Rejected by: {admin_name}"
                await query.edit_message_caption(caption=updated_caption, parse_mode="Markdown")
            except:
                pass 
            # --- (ပြီး) ---
            
            topup_data = db.get_topup_by_id(topup_id)
            topup_amount = topup_data.get("amount", 0) if topup_data else 0

            try:
                await context.bot.send_message(
                    chat_id=int(target_user_id),
                    text=f"❌ ***ငွေဖြည့်မှု ငြင်းပယ်ခံရပါပြီ!***\n\n"
                         f"💰 ***ပမာဏ:*** `{topup_amount:,} MMK`\n"
                         f"👤 ***Rejected by:*** {admin_name}\n\n"
                         f"📞 ***အကြောင်းရင်း သိရှိရန် admin ကို ဆက်သွယ်ပါ။***\n"
                         f"🔓 ***Bot လုပ်ဆောင်ချက်များ ပြန်လည် အသုံးပြုနိုင်ပါပြီ!***",
                    parse_mode="Markdown"
                )
            except:
                pass

            load_admin_ids_global()
            user_doc = db.get_user(target_user_id)
            user_name = user_doc.get("name", "Unknown") if user_doc else "Unknown"
            
            for admin_id in ADMIN_IDS:
                if admin_id != int(user_id):
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"❌ ***Topup Rejected!***\n"
                                 f"🔖 ***Topup ID:*** `{topup_id}`\n"
                                 f"👤 ***User Name:*** [{user_name}](tg://user?id={target_user_id})\n"
                                 f"💰 ***Amount:*** `{topup_amount:,} MMK`\n"
                                 f"👤 ***Rejected by:*** {admin_name}",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
            
            try:
                if await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID):
                    group_msg = (
                        f"❌ ***Topup ငြင်းပယ်ပြီး!***\n\n"
                        f"🔖 ***Topup ID:*** `{topup_id}`\n"
                        f"👤 ***User:*** [{user_name}](tg://user?id={target_user_id})\n"
                        f"💰 ***Amount:*** `{topup_amount:,} MMK`\n"
                        f"👤 ***ငြင်းပယ်သူ:*** {admin_name}\n"
                        f"#TopupRejected"
                    )
                    msg_obj = await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=group_msg, parse_mode="Markdown")
                    
                    db.add_message_to_delete_queue(msg_obj.message_id, msg_obj.chat_id, datetime.now().isoformat())
            except:
                pass

            await query.answer("❌ Topup rejected!", show_alert=True)
        else:
            await query.answer("❌ Topup မတွေ့ရှိပါ သို့မဟုတ် လုပ်ဆောင်ပြီးပါပြီ!")
        return


    elif query.data.startswith("pubg_confirm_"):
        if not is_admin(user_id):
            await query.answer("❌ ***သင်သည် admin မဟုတ်ပါ!***")
            return
        
        order_id = query.data.replace("pubg_confirm_", "")
        updates = {
            "status": "confirmed",
            "confirmed_by": admin_name,
            "confirmed_at": datetime.now().isoformat()
        }
        
        target_user_id = db.find_and_update_order(order_id, updates)
        
        if target_user_id:
            # --- (မူလ Edit Logic) ---
            try:
                await query.edit_message_text(
                    text=query.message.text.replace("⏳ စောင့်ဆိုင်းနေသည်", f"✅ လက်ခံပြီး (by {admin_name})"),
                    parse_mode="Markdown",
                    reply_markup=None
                )
            except: pass
            # --- (ပြီး) ---
            
            order_details = db.get_order_by_id(order_id)
            if not order_details: order_details = {} 

            load_admin_ids_global()
            for admin_id in ADMIN_IDS:
                if admin_id != int(user_id):
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"✅ ***PUBG Order Confirmed!***\n"
                                 f"📝 ***Order ID:*** `{order_id}`\n"
                                 f"👤 ***Confirmed by:*** {admin_name}",
                            parse_mode="Markdown"
                        )
                    except: pass
            
            user_doc = db.get_user(target_user_id)
            user_name = user_doc.get("name", "Unknown") if user_doc else "Unknown"
            
            try:
                if await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID):
                    group_msg = (
                        f"✅ ***PUBG Order လက်ခံပြီး!***\n\n"
                        f"📝 ***Order ID:*** `{order_id}`\n"
                        f"👤 ***User:*** [{user_name}](tg://user?id={target_user_id})\n"
                        f"👤 ***လက်ခံသူ:*** {admin_name}\n"
                        f"#OrderConfirmed #PUBG"
                    )
                    msg_obj = await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=group_msg, parse_mode="Markdown")
                    
                    db.add_message_to_delete_queue(msg_obj.message_id, msg_obj.chat_id, datetime.now().isoformat())
            except:
                pass

            try:
                chat_id = order_details.get("chat_id", int(target_user_id))
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ ***PUBG Order လက်ခံပြီးပါပြီ!***\n\n"
                         f"📝 ***Order ID:*** `{order_id}`\n"
                         f"👤 ***User:*** [{user_name}](tg://user?id={target_user_id})\n"
                         f"📊 Status: ✅ ***လက်ခံပြီး***\n\n"
                         "💎 ***UC များကို ထည့်သွင်းပေးလိုက်ပါပြီ။***",
                    parse_mode="Markdown"
                )
            except:
                pass


            await query.answer("✅ PUBG Order လက်ခံပါပြီ!", show_alert=True)
        else:
            await query.answer("❌ Order မတွေ့ရှိပါ သို့မဟုတ် လုပ်ဆောင်ပြီးပါပြီ!", show_alert=True)
        return
    # --- (PUBG LOGIC ပြီး) ---

    elif query.data.startswith("order_confirm_"):
        if not is_admin(user_id):
            await query.answer("❌ ***သင်သည် admin မဟုတ်ပါ!***")
            return
        
        order_id = query.data.replace("order_confirm_", "")
        updates = {
            "status": "confirmed",
            "confirmed_by": admin_name,
            "confirmed_at": datetime.now().isoformat()
        }
        
        target_user_id = db.find_and_update_order(order_id, updates)
        
        if target_user_id:
 
            try:
                await query.edit_message_text(
                    text=query.message.text.replace("⏳ စောင့်ဆိုင်းနေသည်", f"✅ လက်ခံပြီး (by {admin_name})"),
                    parse_mode="Markdown",
                    reply_markup=None
                )
            except: pass
            # --- (ပြီး) ---
            
            order_details = db.get_order_by_id(order_id)
            if not order_details: order_details = {} 

            load_admin_ids_global()
            for admin_id in ADMIN_IDS:
                if admin_id != int(user_id):
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"✅ ***Order Confirmed!***\n"
                                 f"📝 ***Order ID:*** `{order_id}`\n"
                                 f"👤 ***Confirmed by:*** {admin_name}",
                            parse_mode="Markdown"
                        )
                    except: pass
            
            user_doc = db.get_user(target_user_id)
            user_name = user_doc.get("name", "Unknown") if user_doc else "Unknown"
            
            try:
                if await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID):
                    group_msg = (
                        f"✅ ***Order လက်ခံပြီး!***\n\n"
                        f"📝 ***Order ID:*** `{order_id}`\n"
                        f"👤 ***User:*** [{user_name}](tg://user?id={target_user_id})\n"
                        f"👤 ***လက်ခံသူ:*** {admin_name}\n"
                        f"#OrderConfirmed"
                    )
                    msg_obj = await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=group_msg, parse_mode="Markdown")
                    
                    db.add_message_to_delete_queue(msg_obj.message_id, msg_obj.chat_id, datetime.now().isoformat())
            except:
                pass

            try:
                chat_id = order_details.get("chat_id", int(target_user_id))
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ ***Order လက်ခံပြီးပါပြီ!***\n\n"
                         f"📝 ***Order ID:*** `{order_id}`\n"
                         f"👤 ***User:*** [{user_name}](tg://user?id={target_user_id})\n"
                         f"📊 Status: ✅ ***လက်ခံပြီး***\n\n"
                         "💎 ***Diamonds များကို ထည့်သွင်းပေးလိုက်ပါပြီ။***",
                    parse_mode="Markdown"
                )
            except:
                pass

            # === (COMMISSION LOGIC - နေရာ ၃ - ဖြုတ်ထားပါသည်) ===

            await query.answer("✅ Order လက်ခံပါပြီ!", show_alert=True)
        else:
            await query.answer("❌ Order မတွေ့ရှိပါ သို့မဟုတ် လုပ်ဆောင်ပြီးပါပြီ!", show_alert=True)
        return

    elif query.data.startswith("order_cancel_"):
    
        if not is_admin(user_id):
            await query.answer("❌ ***သင်သည် admin မဟုတ်ပါ!***")
            return
        
        order_id = query.data.replace("order_cancel_", "")
        order_details = db.get_order_by_id(order_id)
        if not order_details:
             await query.answer("❌ Order မတွေ့ရှိပါ!", show_alert=True)
             return
        
        if order_details.get("status") in ["confirmed", "cancelled"]:
            await query.answer("⚠️ Order ကို လုပ်ဆောင်ပြီးပါပြီ!", show_alert=True)
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except: pass
            return
            
        refund_amount = order_details.get("price", 0)
        updates = {
            "status": "cancelled",
            "cancelled_by": admin_name,
            "cancelled_at": datetime.now().isoformat()
        }
        
        target_user_id = db.find_and_update_order(order_id, updates)
        
        if target_user_id:
            db.update_balance(target_user_id, refund_amount) # Refund balance

            # --- (မူလ Edit Logic) ---
            try:
                await query.edit_message_text(
                    text=query.message.text.replace("⏳ စောင့်ဆိုင်းနေသည်", f"❌ ငြင်းပယ်ပြီး (by {admin_name})"),
                    parse_mode="Markdown",
                    reply_markup=None
                )
            except:
                pass
            # --- (ပြီး) ---

            load_admin_ids_global()
            for admin_id in ADMIN_IDS:
                if admin_id != int(user_id):
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"❌ ***Order Cancelled!***\n"
                                 f"📝 ***Order ID:*** `{order_id}`\n"
                                 f"👤 ***Cancelled by:*** {admin_name}\n"
                                 f"💰 ***Refunded:*** {refund_amount:,} MMK",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
            
            user_doc = db.get_user(target_user_id)
            user_name = user_doc.get("name", "Unknown") if user_doc else "Unknown"

            try:
                if await is_bot_admin_in_group(context.bot, ADMIN_GROUP_ID):
                    group_msg = (
                        f"❌ ***Order ငြင်းပယ်ပြီး!***\n\n"
                        f"📝 ***Order ID:*** `{order_id}`\n"
                        f"👤 ***User:*** [{user_name}](tg://user?id={target_user_id})\n"
                        f"💰 ***Refunded:*** {refund_amount:,} MMK`\n"
                        f"👤 ***ငြင်းပယ်သူ:*** {admin_name}\n"
                        f"#OrderCancelled"
                    )
                    msg_obj = await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=group_msg, parse_mode="Markdown")
                    
                    db.add_message_to_delete_queue(msg_obj.message_id, msg_obj.chat_id, datetime.now().isoformat())
            except:
                pass

            try:
                chat_id = order_details.get("chat_id", int(target_user_id))
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ ***Order ငြင်းပယ်ခံရပါပြီ!***\n\n"
                         f"📝 ***Order ID:*** `{order_id}`\n"
                         f"👤 ***User Name:*** [{user_name}](tg://user?id={target_user_id})\n"
                         f"📊 Status: ❌ ငြင်းပယ်ပြီး\n"
                         f"💰 ***ငွေပြန်အမ်း:*** {refund_amount:,} MMK\n\n"
                         "📞 ***အကြောင်းရင်း သိရှိရန် admin ကို ဆက်သွယ်ပါ။***",
                    parse_mode="Markdown"
                )
            except:
                pass

            await query.answer("❌ ***Order ငြင်းပယ်ပြီး ငွေပြန်အမ်းပါပြီ!**", show_alert=True)
        else:
            await query.answer("❌ Order မတွေ့ရှိပါ!", show_alert=True)
        return
        # ... ( order_cancel_ logic ဤနေရာတွင် ပြီးဆုံး ) ...

    # Report filter callbacks
    elif query.data.startswith("report_day_"):
        # ... (ဤနေရာမှ code များ မပြောင်းပါ ... ) ...
        if not is_owner(user_id):
            await query.answer("❌ Owner သာ ကြည့်နိုင်ပါတယ်!", show_alert=True)
            return

        parts = query.data.replace("report_day_", "").split("_")
        if len(parts) == 1:
            start_date = end_date = parts[0]
            period_text = f"ရက် ({start_date})"
        else:
            start_date = parts[1]
            end_date = parts[2]
            period_text = f"ရက် ({start_date} မှ {end_date})"

        all_users = db.get_all_users()
        total_sales = total_orders = total_topups = topup_count = 0
        for user_data in all_users:
            for order in user_data.get("orders", []):
                if order.get("status") == "confirmed" and start_date <= order.get("confirmed_at", "")[:10] <= end_date:
                    total_sales += order["price"]
                    total_orders += 1
            for topup in user_data.get("topups", []):
                if topup.get("status") == "approved" and start_date <= topup.get("approved_at", "")[:10] <= end_date:
                    total_topups += topup["amount"]
                    topup_count += 1

        await query.edit_message_text(
            f"📊 ***Daily Report***\n📅 ***ကာလ:*** {period_text}\n\n"
            f"🛒 ***Order Confirmed***: {total_orders} ခု\n"
            f"💰 ***စုစုပေါင်း အရောင်း:*** `{total_sales:,} MMK`\n\n"
            f"💳 ***Topup Approved***: {topup_count} ခု\n"
            f"💰 ***စုစုပေါင်း ငွေဖြည့်:*** `{total_topups:,} MMK`",
            parse_mode="Markdown"
        )
        return

    elif query.data.startswith("report_month_"):
        # ... (ဤနေရာမှ code များ မပြောင်းပါ ... ) ...
        if not is_owner(user_id):
            await query.answer("❌ Owner သာ ကြည့်နိုင်ပါတယ်!", show_alert=True)
            return

        parts = query.data.replace("report_month_", "").split("_")
        if len(parts) == 1:
            start_month = end_month = parts[0]
            period_text = f"လ ({start_month})"
        else:
            start_month = parts[1]
            end_month = parts[2]
            period_text = f"လ ({start_month} မှ {end_month})"

        all_users = db.get_all_users()
        total_sales = total_orders = total_topups = topup_count = 0
        for user_data in all_users:
            for order in user_data.get("orders", []):
                if order.get("status") == "confirmed" and start_month <= order.get("confirmed_at", "")[:7] <= end_month:
                    total_sales += order["price"]
                    total_orders += 1
            for topup in user_data.get("topups", []):
                if topup.get("status") == "approved" and start_month <= topup.get("approved_at", "")[:7] <= end_month:
                    total_topups += topup["amount"]
                    topup_count += 1

        await query.edit_message_text(
            f"📊 ***Monthly Report***\n📅 ***ကာလ:*** {period_text}\n\n"
            f"🛒 ***Order Confirmed***: {total_orders} ခု\n"
            f"💰 ***စုစုပေါင်း အရောင်း:*** `{total_sales:,} MMK`\n\n"
            f"💳 ***Topup Approved***: {topup_count} ခု\n"
            f"💰 ***စုစုပေါင်း ငွေဖြည့်:*** `{total_topups:,} MMK`",
            parse_mode="Markdown"
        )
        return

    elif query.data.startswith("report_year_"):
        # ... (ဤနေရာမှ code များ မပြောင်းပါ ... ) ...
        if not is_owner(user_id):
            await query.answer("❌ Owner သာ ကြည့်နိုင်ပါတယ်!", show_alert=True)
            return

        parts = query.data.replace("report_year_", "").split("_")
        if len(parts) == 1:
            start_year = end_year = parts[0]
            period_text = f"နှစ် ({start_year})"
        else:
            start_year = parts[1]
            end_year = parts[2]
            period_text = f"နှစ် ({start_year} မှ {end_year})"

        all_users = db.get_all_users()
        total_sales = total_orders = total_topups = topup_count = 0
        for user_data in all_users:
            for order in user_data.get("orders", []):
                if order.get("status") == "confirmed" and start_year <= order.get("confirmed_at", "")[:4] <= end_year:
                    total_sales += order["price"]
                    total_orders += 1
            for topup in user_data.get("topups", []):
                if topup.get("status") == "approved" and start_year <= topup.get("approved_at", "")[:4] <= end_year:
                    total_topups += topup["amount"]
                    topup_count += 1

        await query.edit_message_text(
            f"📊 ***Yearly Report***\n📅 ***ကာလ:*** {period_text}\n\n"
            f"🛒 ***Order Confirmed***: {total_orders} ခု\n"
            f"💰 ***စုစုပေါင်း အရောင်း:*** `{total_sales:,} MMK`\n\n"
            f"💳 ***Topup Approved***: {topup_count} ခု\n"
            f"💰 ***စုစုပေါင်း ငွေဖြည့်:*** `{total_topups:,} MMK`",
            parse_mode="Markdown"
        )
        return

    # Check if user is restricted
    if user_id in user_states and user_states[user_id] == "waiting_approval":
        await query.answer("❌ Screenshot ပို့ပြီးပါပြီ! Admin approve စောင့်ပါ။", show_alert=True)
        return

    if query.data == "copy_kpay":
        # ... (ဤနေရာမှ code များ မပြောင်းပါ ... ) ...
        await query.answer(f"📱 KPay Number copied! {payment_info['kpay_number']}", show_alert=True)
        await query.message.reply_text(
            "📱 ***KBZ Pay Number***\n\n"
            f"`{payment_info['kpay_number']}`\n\n"
            f"👤 Name: ***{payment_info['kpay_name']}***\n"
            "📋 ***Number ကို အပေါ်မှ copy လုပ်ပါ***",
            parse_mode="Markdown"
        )

    elif query.data == "copy_wave":
        # ... (ဤနေရာမှ code များ မပြောင်းပါ ... ) ...
        await query.answer(f"📱 Wave Number copied! {payment_info['wave_number']}", show_alert=True)
        await query.message.reply_text(
            "📱 ***Wave Money Number***\n\n"
            f"`{payment_info['wave_number']}`\n\n"
            f"👤 Name: ***{payment_info['wave_name']}***\n"
            "📋 ***Number ကို အပေါ်မှ copy လုပ်ပါ***",
            parse_mode="Markdown"
        )

    elif query.data == "topup_button":
        # ... (ဤနေရာမှ code များ မပြောင်းပါ ... ) ...
        keyboard = [
            [InlineKeyboardButton("📱 Copy KPay Number", callback_data="copy_kpay")],
            [InlineKeyboardButton("📱 Copy Wave Number", callback_data="copy_wave")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg_text = (
                "💳 ***ငွေဖြည့်လုပ်ငန်းစဉ်***\n\n"
                "1️⃣ `/topup amount` ဥပမာ: `/topup 5000`\n\n"
                "2️⃣ ***အောက်ပါ account သို့ ငွေလွှဲပါ***:\n"
                f"📱 ***KBZ Pay:*** `{payment_info['kpay_number']}` ({payment_info['kpay_name']})\n"
                f"📱 ***Wave Money:*** `{payment_info['wave_number']}` ({payment_info['wave_name']})\n\n"
                "3️⃣ ***Screenshot ကို ဒီ chat မှာ တင်ပါ***\n"
                "⏰ ***Admin က စစ်ဆေးပြီး approve လုပ်ပါမည်။***"
        )
        try:
            await query.edit_message_text(
                text=msg_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except Exception:
            await query.message.reply_text(
                text=msg_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )


def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN environment variable မရှိပါ!")
        return

    # Load all settings from DB on startup
    load_global_settings()
    load_authorized_users() 
    load_admin_ids_global()

   
    application = Application.builder().token(BOT_TOKEN).build()
    
    job_queue = application.job_queue
    job_queue.run_repeating(auto_delete_job, interval=3600, first=10) 

    # User commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("mmb", mmb_command))
    application.add_handler(CommandHandler("pubg", pubg_command)) # <-- PUBG command ထည့်ပြီး
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("topup", topup_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    # application.add_handler(CommandHandler("c", c_command)) # Auto-calc ကြောင့် ဖြုတ်ထား
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("pubgprice", pubg_price_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("clearhistory", clear_history_command)) # history.py မှ
    application.add_handler(CommandHandler("affiliate", affiliate_command)) # <-- Affiliate command ထည့်ပြီး

    # Admin commands
    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("deduct", deduct_command))
    application.add_handler(CommandHandler("addrefund", addrefund_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("reply", reply_command))
    application.add_handler(CommandHandler("checkuser", check_user_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("addadm", addadm_command))
    application.add_handler(CommandHandler("unadm", unadm_command))
    application.add_handler(CommandHandler("sendgroup", send_to_group_command))
    application.add_handler(CommandHandler("maintenance", maintenance_command))
    application.add_handler(CommandHandler("testgroup", testgroup_command))
    application.add_handler(CommandHandler("adminhelp", adminhelp_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("cleanmongodb", clean_mongodb_command))
    application.add_handler(CommandHandler("setpercentage", setpercentage_command))
    application.add_handler(CommandHandler("autodelete", set_auto_delete_command))
    application.add_handler(CommandHandler("checkallusers", check_all_users_command))
    application.add_handler(CommandHandler("cleanpython", clean_python_command))

    # Price & Payment Settings
    application.add_handler(CommandHandler("setprice", setprice_command))
    application.add_handler(CommandHandler("removeprice", removeprice_command))
    application.add_handler(CommandHandler("setpubgprice", setpubgprice_command)) # <-- PUBG command ထည့်ပြီး
    application.add_handler(CommandHandler("removepubgprice", removepubgprice_command)) # <-- PUBG command ထည့်ပြီး
    application.add_handler(CommandHandler("setwavenum", setwavenum_command))
    application.add_handler(CommandHandler("setkpaynum", setkpaynum_command))
    application.add_handler(CommandHandler("setwavename", setwavename_command))
    application.add_handler(CommandHandler("setkpayname", setkpayname_command))
    application.add_handler(CommandHandler("setkpayqr", setkpayqr_command))
    application.add_handler(CommandHandler("removekpayqr", removekpayqr_command))
    application.add_handler(CommandHandler("setwaveqr", setwaveqr_command))
    application.add_handler(CommandHandler("removewaveqr", removewaveqr_command))

    # Report commands
    application.add_handler(CommandHandler("d", daily_report_command))
    application.add_handler(CommandHandler("m", monthly_report_command))
    application.add_handler(CommandHandler("y", yearly_report_command))

    
    # .sasukemlbbtopup command
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^\.sasukemlbbtopup'), sasukemlbbtopup_command))

    # Callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Message handlers
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_members))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_left_chat_member))
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.VOICE | filters.Sticker.ALL | filters.VIDEO |
         filters.ANIMATION | filters.AUDIO | filters.Document.ALL |
         filters.FORWARDED | filters.POLL) & ~filters.COMMAND,
        handle_restricted_content
    ))

    print("🤖 Bot စတင်နေပါသည် - 24/7 Running Mode (MongoDB Connected)")
    print("✅ Settings, Orders, Topups, AI စလုံးအဆင်သင့်ပါ")
    print("🔧 Admin commands များ အသုံးပြုနိုင်ပါပြီ")

    # Run main bot
    application.run_polling()

if __name__ == "__main__":
    main()
    
 

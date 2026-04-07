import os
from telegram import Update
from telegram.ext import ContextTypes
import database as db

def is_owner(user_id):
    try:
        ADMIN_ID = int(os.environ.get("ADMIN_ID"))
        return int(user_id) == ADMIN_ID
    except:
        return False

async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not is_owner(user_id):
        await update.message.reply_text("")
        return

    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text(
            "❌ Format မှားနေပါပြီ!\n"
            parse_mode="Markdown"
        )
        return

    target_user_id = args[0]
    
    user_data = db.get_user(target_user_id)
    if not user_data:
        await update.message.reply_text(f"")
        return
        
    success = db.clear_user_history(target_user_id)

    if success:
        await update.message.reply_text(
            f"✅ **Success!**"
        )
    else:
        await update.message.reply_text("")

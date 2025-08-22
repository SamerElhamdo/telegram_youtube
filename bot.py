import os
import asyncio
import logging
from typing import Dict, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode
import yt_dlp
import aiofiles
from dotenv import load_dotenv

# تحميل المتغيرات البيئية
load_dotenv()

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# إعدادات البوت
BOT_TOKEN = os.getenv('BOT_TOKEN')
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH', './downloads/')

# إنشاء مجلد التحميل إذا لم يكن موجوداً
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

class YouTubeTelegramBot:
    def __init__(self):
        self.user_sessions: Dict[int, Dict] = {}
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /start"""
        welcome_message = """
🎬 مرحباً بك في بوت تحميل الفيديوهات!

📋 الميزات المتاحة:
• تحميل فيديوهات من يوتيوب
• اختيار جودة الفيديو
• اختيار صيغة التحميل (فيديو/صوت)

📝 كيفية الاستخدام:
1. أرسل رابط الفيديو من يوتيوب
2. اختر الجودة المطلوبة
3. اختر الصيغة (فيديو أو صوت فقط)
4. انتظر التحميل والإرسال

🔗 أرسل رابط الفيديو الآن!
        """
        
        await update.message.reply_text(
            welcome_message,
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الروابط المرسلة"""
        url = update.message.text.strip()
        user_id = update.message.from_user.id
        
        # التحقق من صحة الرابط
        if not self.is_valid_youtube_url(url):
            await update.message.reply_text(
                "❌ الرابط غير صحيح!\n"
                "يرجى إرسال رابط صحيح من يوتيوب."
            )
            return
        
        # إرسال رسالة انتظار
        loading_message = await update.message.reply_text(
            "🔍 جاري تحليل الفيديو...\nيرجى الانتظار..."
        )
        
        try:
            # الحصول على معلومات الفيديو
            video_info = await self.get_video_info(url)
            
            if not video_info:
                await loading_message.edit_text(
                    "❌ فشل في تحليل الفيديو!\n"
                    "يرجى التأكد من صحة الرابط والمحاولة مرة أخرى."
                )
                return
            
            # حفظ معلومات الجلسة
            self.user_sessions[user_id] = {
                'url': url,
                'video_info': video_info,
                'message_id': loading_message.message_id
            }
            
            # إنشاء أزرار الخيارات
            keyboard = self.create_quality_keyboard(video_info)
            
            video_title = video_info.get('title', 'غير معروف')[:50]
            duration = self.format_duration(video_info.get('duration', 0))
            uploader = video_info.get('uploader', 'غير معروف')
            
            info_text = f"""
📹 **معلومات الفيديو:**

🎬 **العنوان:** {video_title}
👤 **القناة:** {uploader}
⏱️ **المدة:** {duration}

📊 اختر جودة التحميل:
            """
            
            await loading_message.edit_text(
                info_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الرابط: {e}")
            await loading_message.edit_text(
                "❌ حدث خطأ أثناء معالجة الرابط!\n"
                "يرجى المحاولة مرة أخرى."
            )

    def is_valid_youtube_url(self, url: str) -> bool:
        """التحقق من صحة رابط يوتيوب"""
        youtube_domains = ['youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com']
        return any(domain in url for domain in youtube_domains)

    async def get_video_info(self, url: str) -> Dict:
        """الحصول على معلومات الفيديو"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                return info
        except Exception as e:
            logger.error(f"خطأ في استخراج معلومات الفيديو: {e}")
            return None

    def create_quality_keyboard(self, video_info: Dict) -> InlineKeyboardMarkup:
        """إنشاء لوحة مفاتيح اختيار الجودة"""
        keyboard = []
        
        # جودات الفيديو المتاحة
        formats = video_info.get('formats', [])
        video_formats = {}
        
        for fmt in formats:
            if fmt.get('vcodec') != 'none' and fmt.get('height'):
                height = fmt.get('height')
                ext = fmt.get('ext', 'mp4')
                if height not in video_formats or fmt.get('filesize', 0) > video_formats[height].get('filesize', 0):
                    video_formats[height] = fmt
        
        # ترتيب الجودات من الأعلى للأقل
        sorted_qualities = sorted(video_formats.keys(), reverse=True)
        
        # إضافة أزرار الجودة
        for quality in sorted_qualities[:6]:  # أول 6 جودات
            quality_text = f"📹 {quality}p"
            callback_data = f"video_{quality}"
            keyboard.append([InlineKeyboardButton(quality_text, callback_data=callback_data)])
        
        # إضافة خيار الصوت فقط
        keyboard.append([InlineKeyboardButton("🎵 صوت فقط (MP3)", callback_data="audio_mp3")])
        
        # إضافة زر الإلغاء
        keyboard.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel")])
        
        return InlineKeyboardMarkup(keyboard)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الأزرار"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if user_id not in self.user_sessions:
            await query.edit_message_text("❌ انتهت صلاحية الجلسة. يرجى إرسال رابط جديد.")
            return
        
        if data == "cancel":
            del self.user_sessions[user_id]
            await query.edit_message_text("❌ تم إلغاء العملية.")
            return
        
        session = self.user_sessions[user_id]
        
        # تحديث رسالة التحميل
        await query.edit_message_text(
            "⬇️ جاري التحميل...\nيرجى الانتظار، قد تستغرق العملية بضع دقائق."
        )
        
        try:
            if data.startswith("video_"):
                quality = data.split("_")[1]
                file_path = await self.download_video(session['url'], quality)
            elif data.startswith("audio_"):
                file_path = await self.download_audio(session['url'])
            else:
                await query.edit_message_text("❌ خيار غير صحيح!")
                return
            
            if file_path and os.path.exists(file_path):
                # إرسال الملف
                await self.send_file(query, file_path)
                
                # حذف الملف بعد الإرسال
                os.remove(file_path)
            else:
                await query.edit_message_text("❌ فشل في تحميل الملف!")
                
        except Exception as e:
            logger.error(f"خطأ في التحميل: {e}")
            await query.edit_message_text("❌ حدث خطأ أثناء التحميل!")
        
        finally:
            # تنظيف الجلسة
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]

    async def download_video(self, url: str, quality: str) -> str:
        """تحميل الفيديو بجودة محددة"""
        output_path = os.path.join(DOWNLOAD_PATH, f"video_{quality}p_%(title)s.%(ext)s")
        
        ydl_opts = {
            'format': f'best[height<={quality}]/best',
            'outtmpl': output_path,
            'quiet': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                filename = ydl.prepare_filename(info)
                return filename
        except Exception as e:
            logger.error(f"خطأ في تحميل الفيديو: {e}")
            return None

    async def download_audio(self, url: str) -> str:
        """تحميل الصوت فقط"""
        output_path = os.path.join(DOWNLOAD_PATH, "audio_%(title)s.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                filename = ydl.prepare_filename(info)
                # تغيير امتداد الملف إلى mp3
                audio_filename = os.path.splitext(filename)[0] + '.mp3'
                return audio_filename
        except Exception as e:
            logger.error(f"خطأ في تحميل الصوت: {e}")
            return None

    async def send_file(self, query, file_path: str):
        """إرسال الملف للمستخدم"""
        file_size = os.path.getsize(file_path)
        
        # التحقق من حجم الملف (حد تلجرام 50 ميجا)
        if file_size > 50 * 1024 * 1024:
            await query.edit_message_text(
                "❌ حجم الملف كبير جداً (أكثر من 50 ميجا)!\n"
                "يرجى اختيار جودة أقل."
            )
            return
        
        filename = os.path.basename(file_path)
        
        try:
            if file_path.endswith('.mp3'):
                # إرسال كملف صوتي
                with open(file_path, 'rb') as audio_file:
                    await query.message.reply_audio(
                        audio=audio_file,
                        caption="🎵 تم تحميل الملف الصوتي بنجاح!",
                        filename=filename
                    )
            else:
                # إرسال كفيديو
                with open(file_path, 'rb') as video_file:
                    await query.message.reply_video(
                        video=video_file,
                        caption="📹 تم تحميل الفيديو بنجاح!",
                        filename=filename
                    )
            
            await query.edit_message_text("✅ تم إرسال الملف بنجاح!")
            
        except Exception as e:
            logger.error(f"خطأ في إرسال الملف: {e}")
            await query.edit_message_text("❌ فشل في إرسال الملف!")

    def format_duration(self, seconds: int) -> str:
        """تنسيق مدة الفيديو"""
        if not seconds:
            return "غير محدد"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

def main():
    """تشغيل البوت"""
    if not BOT_TOKEN:
        print("❌ خطأ: لم يتم العثور على BOT_TOKEN في متغيرات البيئة!")
        return
    
    # إنشاء البوت
    bot = YouTubeTelegramBot()
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة معالجات الأوامر
    application.add_handler(CommandHandler("start", bot.start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_url))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    
    print("🚀 بدء تشغيل البوت...")
    print("📝 أرسل /start للبدء")
    
    # تشغيل البوت
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

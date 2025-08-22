import os
import asyncio
import logging
import random
import time
from typing import Dict, List, Optional
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
USE_PROXY = os.getenv('USE_PROXY', 'false').lower() == 'true'
PROXY_URL = os.getenv('PROXY_URL', '')

# إنشاء مجلد التحميل إذا لم يكن موجوداً
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# قائمة User Agents عشوائية لتجنب اكتشاف البوت
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
]

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
            
            # معالجة الأخطاء المختلفة
            if 'error' in video_info:
                error_type = video_info.get('error')
                error_messages = {
                    'geo_restricted': "🌍 **الفيديو غير متاح في بلدك**\n\n"
                                    "💡 **الحلول المقترحة:**\n"
                                    "• استخدم VPN للاتصال من بلد آخر\n"
                                    "• جرب رابطاً آخر من نفس القناة\n"
                                    "• تواصل مع المسؤول لإعداد بروكسي",
                    
                    'login_required': "🔒 **يوتيوب يطلب تسجيل الدخول**\n\n"
                                    "💡 **الحلول المقترحة:**\n"
                                    "• انتظر قليلاً وحاول مرة أخرى\n"
                                    "• استخدم VPN للتغيير من موقعك\n"
                                    "• جرب فيديو آخر من قناة مختلفة",
                    
                    'unavailable': "❌ **الفيديو غير متاح**\n\n"
                                 "💡 **الأسباب المحتملة:**\n"
                                 "• الفيديو محذوف أو خاص\n"
                                 "• القناة محظورة أو معلقة\n"
                                 "• مشكلة مؤقتة في يوتيوب",
                    
                    'extraction_failed': "⚠️ **فشل في استخراج معلومات الفيديو**\n\n"
                                       "💡 **جرب:**\n"
                                       "• إعادة إرسال الرابط\n"
                                       "• التأكد من صحة الرابط\n"
                                       "• المحاولة لاحقاً",
                }
                
                error_msg = error_messages.get(error_type, "❌ حدث خطأ غير معروف!")
                await loading_message.edit_text(error_msg, parse_mode=ParseMode.MARKDOWN)
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

    def get_ydl_opts(self, for_download: bool = False) -> Dict:
        """إنشاء خيارات yt-dlp محسنة"""
        opts = {
            'quiet': True,
            'no_warnings': True,
            'user_agent': random.choice(USER_AGENTS),
            'sleep_interval': random.uniform(1, 3),
            'max_sleep_interval': 5,
            'extractor_retries': 3,
            'fragment_retries': 3,
            'retry_sleep_functions': {
                'http': lambda n: random.uniform(1, 3) * (2 ** n),
                'fragment': lambda n: random.uniform(1, 2) * (2 ** n),
            },
            # إعدادات لتجنب اكتشاف البوت
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            # تجاهل الأخطاء المؤقتة
            'ignoreerrors': False,
            'extract_flat': False,
        }
        
        # إضافة البروكسي إذا كان متاحاً
        if USE_PROXY and PROXY_URL:
            opts['proxy'] = PROXY_URL
            logger.info("استخدام البروكسي للاتصال")
        
        # إعدادات إضافية للتحميل
        if for_download:
            opts.update({
                'writesubtitles': False,
                'writeautomaticsub': False,
                'writedescription': False,
                'writeinfojson': False,
                'writethumbnail': False,
            })
        
        return opts

    async def get_video_info(self, url: str) -> Optional[Dict]:
        """الحصول على معلومات الفيديو مع معالجة أفضل للأخطاء"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # إضافة تأخير عشوائي بين المحاولات
                if attempt > 0:
                    delay = random.uniform(2, 5) * attempt
                    logger.info(f"إعادة المحاولة {attempt + 1} بعد {delay:.1f} ثانية...")
                    await asyncio.sleep(delay)
                
                ydl_opts = self.get_ydl_opts()
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                    return info
                    
            except yt_dlp.utils.GeoRestrictedError as e:
                logger.error(f"الفيديو غير متاح في هذا البلد: {e}")
                return {'error': 'geo_restricted', 'message': str(e)}
                
            except yt_dlp.utils.ExtractorError as e:
                error_msg = str(e).lower()
                if 'sign in' in error_msg or 'not a bot' in error_msg:
                    logger.error(f"يوتيوب يطلب تسجيل الدخول: {e}")
                    return {'error': 'login_required', 'message': str(e)}
                elif 'private' in error_msg or 'unavailable' in error_msg:
                    logger.error(f"الفيديو غير متاح: {e}")
                    return {'error': 'unavailable', 'message': str(e)}
                else:
                    logger.error(f"خطأ في استخراج الفيديو: {e}")
                    if attempt == max_retries - 1:
                        return {'error': 'extraction_failed', 'message': str(e)}
                    
            except Exception as e:
                logger.error(f"خطأ عام في استخراج معلومات الفيديو: {e}")
                if attempt == max_retries - 1:
                    return {'error': 'unknown', 'message': str(e)}
        
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

    async def download_video(self, url: str, quality: str) -> Optional[str]:
        """تحميل الفيديو بجودة محددة مع معالجة محسنة للأخطاء"""
        output_path = os.path.join(DOWNLOAD_PATH, f"video_{quality}p_%(title)s.%(ext)s")
        
        ydl_opts = self.get_ydl_opts(for_download=True)
        ydl_opts.update({
            'format': f'best[height<={quality}]/best',
            'outtmpl': output_path,
        })
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = random.uniform(3, 6)
                    logger.info(f"إعادة محاولة التحميل بعد {delay:.1f} ثانية...")
                    await asyncio.sleep(delay)
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                    filename = ydl.prepare_filename(info)
                    
                    # التحقق من وجود الملف
                    if os.path.exists(filename):
                        return filename
                    
                    # البحث عن الملف بامتدادات مختلفة
                    base_name = os.path.splitext(filename)[0]
                    for ext in ['.mp4', '.webm', '.mkv', '.avi']:
                        test_file = base_name + ext
                        if os.path.exists(test_file):
                            return test_file
                    
                    logger.error(f"لم يتم العثور على الملف المحمل: {filename}")
                    
            except Exception as e:
                logger.error(f"خطأ في تحميل الفيديو (محاولة {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return None
        
        return None

    async def download_audio(self, url: str) -> Optional[str]:
        """تحميل الصوت فقط مع معالجة محسنة للأخطاء"""
        output_path = os.path.join(DOWNLOAD_PATH, "audio_%(title)s.%(ext)s")
        
        ydl_opts = self.get_ydl_opts(for_download=True)
        ydl_opts.update({
            'format': 'bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = random.uniform(3, 6)
                    logger.info(f"إعادة محاولة تحميل الصوت بعد {delay:.1f} ثانية...")
                    await asyncio.sleep(delay)
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                    filename = ydl.prepare_filename(info)
                    
                    # البحث عن ملف MP3
                    audio_filename = os.path.splitext(filename)[0] + '.mp3'
                    if os.path.exists(audio_filename):
                        return audio_filename
                    
                    # البحث عن ملفات صوتية أخرى
                    base_name = os.path.splitext(filename)[0]
                    for ext in ['.m4a', '.webm', '.ogg', '.wav']:
                        test_file = base_name + ext
                        if os.path.exists(test_file):
                            return test_file
                    
                    logger.error(f"لم يتم العثور على الملف الصوتي: {audio_filename}")
                    
            except Exception as e:
                logger.error(f"خطأ في تحميل الصوت (محاولة {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return None
        
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

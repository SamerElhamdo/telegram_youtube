import os
import asyncio
import logging
import random
import time
import requests
import urllib.parse
import re
import json
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
        self.proxy_status: Dict[str, bool] = {}  # كاش لحالة البروكسي
        
    def extract_video_id(self, url: str) -> Optional[str]:
        """استخراج معرف الفيديو من رابط يوتيوب باستخدام regex"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})',
            r'youtu\.be\/([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                logger.info(f"تم استخراج معرف الفيديو: {video_id}")
                return video_id
        
        logger.warning(f"فشل في استخراج معرف الفيديو من: {url}")
        return None
    
    async def get_video_info_direct(self, video_id: str) -> Optional[Dict]:
        """الحصول على معلومات الفيديو مباشرة من يوتيوب بدون yt-dlp"""
        try:
            # استخدام طرق مختلفة للحصول على معلومات الفيديو
            methods = [
                self._get_video_info_method1,
                self._get_video_info_method2,
                self._get_video_info_method3
            ]
            
            for method in methods:
                try:
                    result = await method(video_id)
                    if result and 'title' in result:
                        logger.info(f"نجح في الحصول على معلومات الفيديو باستخدام الطريقة: {method.__name__}")
                        return result
                except Exception as e:
                    logger.warning(f"فشل في {method.__name__}: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"خطأ في get_video_info_direct: {e}")
            return None
    
    async def _get_video_info_method1(self, video_id: str) -> Optional[Dict]:
        """الطريقة الأولى: استخدام YouTube oEmbed API"""
        try:
            url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            
            proxies = {'http': PROXY_URL, 'https': PROXY_URL} if USE_PROXY and PROXY_URL else None
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            
            response = await asyncio.to_thread(
                requests.get, url, 
                proxies=proxies, 
                headers=headers, 
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'id': video_id,
                    'title': data.get('title', 'غير معروف'),
                    'uploader': data.get('author_name', 'غير معروف'),
                    'duration': 0,  # oEmbed لا يوفر المدة
                    'thumbnail': data.get('thumbnail_url', ''),
                    'webpage_url': f"https://www.youtube.com/watch?v={video_id}",
                    'method': 'oembed'
                }
            
        except Exception as e:
            logger.warning(f"فشل في oEmbed API: {e}")
            raise
        
        return None
    
    async def _get_video_info_method2(self, video_id: str) -> Optional[Dict]:
        """الطريقة الثانية: scraping صفحة الفيديو"""
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            proxies = {'http': PROXY_URL, 'https': PROXY_URL} if USE_PROXY and PROXY_URL else None
            headers = {
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            response = await asyncio.to_thread(
                requests.get, url, 
                proxies=proxies, 
                headers=headers, 
                timeout=15
            )
            
            if response.status_code == 200:
                html = response.text
                
                # استخراج العنوان
                title_match = re.search(r'<title>(.+?) - YouTube</title>', html)
                title = title_match.group(1) if title_match else 'غير معروف'
                
                # استخراج اسم القناة
                channel_match = re.search(r'"ownerChannelName":"([^"]+)"', html)
                uploader = channel_match.group(1) if channel_match else 'غير معروف'
                
                # استخراج المدة
                duration_match = re.search(r'"lengthSeconds":"(\d+)"', html)
                duration = int(duration_match.group(1)) if duration_match else 0
                
                # استخراج الصورة المصغرة
                thumbnail_match = re.search(r'"playerMicroformatRenderer".*?"thumbnail".*?"url":"([^"]+)"', html)
                thumbnail = thumbnail_match.group(1).replace('\\', '') if thumbnail_match else ''
                
                return {
                    'id': video_id,
                    'title': title,
                    'uploader': uploader,
                    'duration': duration,
                    'thumbnail': thumbnail,
                    'webpage_url': url,
                    'method': 'scraping'
                }
                
        except Exception as e:
            logger.warning(f"فشل في scraping: {e}")
            raise
        
        return None
    
    async def _get_video_info_method3(self, video_id: str) -> Optional[Dict]:
        """الطريقة الثالثة: محاولة استخدام YouTube Data API v3 (إذا كان متاحاً)"""
        try:
            # هذه الطريقة تحتاج API key، لكن يمكن إضافتها لاحقاً
            # حالياً سنرجع None لتجربة الطرق الأخرى
            return None
            
        except Exception as e:
            logger.warning(f"فشل في YouTube Data API: {e}")
            raise
        
    async def test_proxy_connection(self) -> Dict[str, any]:
        """اختبار اتصال البروكسي"""
        if not USE_PROXY or not PROXY_URL:
            return {'status': 'disabled', 'message': 'البروكسي غير مفعل'}
        
        # التحقق من الكاش أولاً
        cache_key = PROXY_URL
        if cache_key in self.proxy_status:
            return {'status': 'cached', 'working': self.proxy_status[cache_key]}
        
        test_urls = [
            'http://httpbin.org/ip',
            'http://ipinfo.io/json',
            'https://api.ipify.org?format=json'
        ]
        
        for test_url in test_urls:
            try:
                # إعداد البروكسي للطلب
                proxies = {'http': PROXY_URL, 'https': PROXY_URL}
                
                # إجراء طلب اختبار مع timeout قصير
                response = await asyncio.to_thread(
                    requests.get, 
                    test_url, 
                    proxies=proxies, 
                    timeout=10,
                    headers={'User-Agent': random.choice(USER_AGENTS)}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    proxy_ip = data.get('origin', data.get('ip', 'غير معروف'))
                    
                    # حفظ في الكاش
                    self.proxy_status[cache_key] = True
                    
                    logger.info(f"البروكسي يعمل بنجاح! IP الجديد: {proxy_ip}")
                    return {
                        'status': 'success',
                        'working': True,
                        'proxy_ip': proxy_ip,
                        'test_url': test_url
                    }
                    
            except Exception as e:
                logger.warning(f"فشل اختبار البروكسي مع {test_url}: {e}")
                continue
        
        # فشل جميع الاختبارات
        self.proxy_status[cache_key] = False
        logger.error("فشل في الاتصال بالبروكسي!")
        return {
            'status': 'failed',
            'working': False,
            'message': 'فشل في الاتصال بالبروكسي'
        }
        
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

📋 **الأوامر المتاحة:**
• `/test [video_id]` - اختبار الطرق البديلة
• `/proxy` - فحص حالة البروكسي
        """
        
        await update.message.reply_text(
            welcome_message,
            parse_mode=ParseMode.MARKDOWN
        )

    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """اختبار الطرق البديلة لاستخراج معلومات الفيديو"""
        if not context.args:
            await update.message.reply_text(
                "❌ يرجى تحديد معرف الفيديو أو رابط كامل\n"
                "مثال: `/test dQw4w9WgXcQ`\n"
                "أو: `/test https://www.youtube.com/watch?v=dQw4w9WgXcQ`"
            )
            return
        
        input_text = context.args[0]
        
        # محاولة استخراج معرف الفيديو
        if input_text.startswith('http'):
            video_id = self.extract_video_id(input_text)
            if not video_id:
                await update.message.reply_text("❌ فشل في استخراج معرف الفيديو من الرابط")
                return
        else:
            video_id = input_text
        
        test_message = await update.message.reply_text(
            f"🧪 جاري اختبار الطرق البديلة لمعرف الفيديو: `{video_id}`",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # اختبار الطرق البديلة
            result = await self.get_video_info_direct(video_id)
            
            if result and 'title' in result:
                method = result.get('method', 'غير معروف')
                title = result.get('title', 'غير معروف')
                uploader = result.get('uploader', 'غير معروف')
                duration = self.format_duration(result.get('duration', 0))
                
                success_msg = f"""
✅ **نجح الاختبار!**

🎬 **العنوان:** {title[:50]}
👤 **القناة:** {uploader}
⏱️ **المدة:** {duration}
🔧 **الطريقة:** {method}

💡 الطرق البديلة تعمل بنجاح!
                """
                
                await test_message.edit_text(success_msg, parse_mode=ParseMode.MARKDOWN)
            else:
                await test_message.edit_text(
                    "❌ فشل في جميع الطرق البديلة\n"
                    "قد يكون الفيديو غير متاح أو محذوف"
                )
                
        except Exception as e:
            logger.error(f"خطأ في اختبار الطرق البديلة: {e}")
            await test_message.edit_text(
                f"❌ حدث خطأ أثناء الاختبار:\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN
            )

    async def proxy_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فحص حالة البروكسي"""
        status_message = await update.message.reply_text("🌐 جاري فحص حالة البروكسي...")
        
        try:
            proxy_test = await self.test_proxy_connection()
            
            if proxy_test['status'] == 'disabled':
                await status_message.edit_text(
                    "ℹ️ **حالة البروكسي:** غير مفعل\n\n"
                    "لتفعيل البروكسي، قم بتعديل ملف `.env`:\n"
                    "```\n"
                    "USE_PROXY=true\n"
                    "PROXY_URL=http://user:pass@proxy:port\n"
                    "```",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif proxy_test['status'] == 'success':
                proxy_ip = proxy_test.get('proxy_ip', 'غير معروف')
                test_url = proxy_test.get('test_url', 'غير معروف')
                
                await status_message.edit_text(
                    f"✅ **البروكسي يعمل بنجاح!**\n\n"
                    f"🌐 **IP الحالي:** `{proxy_ip}`\n"
                    f"🔗 **تم الاختبار مع:** {test_url}\n"
                    f"📡 **حالة الاتصال:** متصل",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await status_message.edit_text(
                    "❌ **فشل في الاتصال بالبروكسي!**\n\n"
                    "💡 **تحقق من:**\n"
                    "• صحة بيانات البروكسي في ملف .env\n"
                    "• أن البروكسي متاح ويعمل\n"
                    "• الاتصال بالإنترنت",
                    parse_mode=ParseMode.MARKDOWN
                )
                
        except Exception as e:
            logger.error(f"خطأ في فحص البروكسي: {e}")
            await status_message.edit_text(
                f"❌ حدث خطأ أثناء فحص البروكسي:\n`{str(e)}`",
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
        
        # فحص البروكسي إذا كان مفعلاً
        if USE_PROXY and PROXY_URL:
            await loading_message.edit_text(
                "🔍 جاري تحليل الفيديو...\n🌐 فحص اتصال البروكسي..."
            )
            
            proxy_test = await self.test_proxy_connection()
            if proxy_test['status'] == 'failed':
                await loading_message.edit_text(
                    "❌ **فشل في الاتصال بالبروكسي!**\n\n"
                    "💡 **الحلول المقترحة:**\n"
                    "• تحقق من صحة بيانات البروكسي في ملف .env\n"
                    "• جرب بروكسي آخر\n"
                    "• تعطيل البروكسي مؤقتاً (USE_PROXY=false)\n\n"
                    "🔧 **تفاصيل الخطأ:** البروكسي غير متاح أو بيانات خاطئة",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            elif proxy_test['status'] == 'success':
                proxy_ip = proxy_test.get('proxy_ip', 'غير معروف')
                await loading_message.edit_text(
                    f"🔍 جاري تحليل الفيديو...\n"
                    f"🌐 البروكسي متصل بنجاح! IP: {proxy_ip}"
                )
                await asyncio.sleep(1)  # عرض رسالة النجاح لثانية واحدة
        
        await loading_message.edit_text(
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
        """الحصول على معلومات الفيديو مع طرق بديلة لتجنب مشاكل yt-dlp"""
        
        # أولاً: محاولة استخراج معرف الفيديو واستخدام الطرق البديلة
        video_id = self.extract_video_id(url)
        if video_id:
            logger.info(f"جاري تجريب الطرق البديلة لمعرف الفيديو: {video_id}")
            
            # تجريب الطرق البديلة أولاً
            direct_info = await self.get_video_info_direct(video_id)
            if direct_info and 'title' in direct_info:
                logger.info(f"نجح في الحصول على معلومات الفيديو بالطريقة البديلة: {direct_info.get('method', 'unknown')}")
                return direct_info
        
        # إذا فشلت الطرق البديلة، جرب yt-dlp
        logger.info("جاري تجريب yt-dlp كخيار احتياطي...")
        max_retries = 2  # تقليل عدد المحاولات لـ yt-dlp
        
        for attempt in range(max_retries):
            try:
                # إضافة تأخير عشوائي بين المحاولات
                if attempt > 0:
                    delay = random.uniform(3, 6) * attempt
                    logger.info(f"إعادة المحاولة مع yt-dlp {attempt + 1} بعد {delay:.1f} ثانية...")
                    await asyncio.sleep(delay)
                
                ydl_opts = self.get_ydl_opts()
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                    if info:
                        info['method'] = 'yt-dlp'
                        return info
                    
            except yt_dlp.utils.GeoRestrictedError as e:
                logger.error(f"الفيديو غير متاح في هذا البلد: {e}")
                return {'error': 'geo_restricted', 'message': str(e)}
                
            except yt_dlp.utils.ExtractorError as e:
                error_msg = str(e).lower()
                if 'sign in' in error_msg or 'not a bot' in error_msg:
                    logger.error(f"يوتيوب يطلب تسجيل الدخول - جاري تجريب الطرق البديلة: {e}")
                    
                    # إذا كان لدينا معرف الفيديو، جرب الطرق البديلة مرة أخرى مع تأخير
                    if video_id:
                        await asyncio.sleep(random.uniform(2, 4))
                        direct_info = await self.get_video_info_direct(video_id)
                        if direct_info:
                            return direct_info
                    
                    return {'error': 'login_required', 'message': str(e)}
                    
                elif 'private' in error_msg or 'unavailable' in error_msg:
                    logger.error(f"الفيديو غير متاح: {e}")
                    return {'error': 'unavailable', 'message': str(e)}
                else:
                    logger.error(f"خطأ في استخراج الفيديو: {e}")
                    if attempt == max_retries - 1:
                        return {'error': 'extraction_failed', 'message': str(e)}
                    
            except Exception as e:
                logger.error(f"خطأ عام في yt-dlp: {e}")
                if attempt == max_retries - 1:
                    # محاولة أخيرة بالطرق البديلة
                    if video_id:
                        logger.info("محاولة أخيرة بالطرق البديلة...")
                        direct_info = await self.get_video_info_direct(video_id)
                        if direct_info:
                            return direct_info
                    
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
    application.add_handler(CommandHandler("test", bot.test_command))
    application.add_handler(CommandHandler("proxy", bot.proxy_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_url))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    
    print("🚀 بدء تشغيل البوت...")
    print("📝 أرسل /start للبدء")
    
    # تشغيل البوت
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

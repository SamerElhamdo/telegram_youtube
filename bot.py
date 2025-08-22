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
    
    async def extract_download_links(self, video_id: str) -> Optional[Dict]:
        """استخراج روابط التحميل المباشرة من يوتيوب"""
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            proxies = {'http': PROXY_URL, 'https': PROXY_URL} if USE_PROXY and PROXY_URL else None
            headers = {
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
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
            
            if response.status_code != 200:
                logger.error(f"فشل في الحصول على صفحة الفيديو: {response.status_code}")
                return None
            
            html = response.text
            
            # البحث عن بيانات التكوين الخاصة بالمشغل
            config_patterns = [
                r'ytInitialPlayerResponse\s*=\s*({.+?});',
                r'var\s+ytInitialPlayerResponse\s*=\s*({.+?});',
                r'window\["ytInitialPlayerResponse"\]\s*=\s*({.+?});'
            ]
            
            player_config = None
            for pattern in config_patterns:
                match = re.search(pattern, html)
                if match:
                    try:
                        player_config = json.loads(match.group(1))
                        logger.info("تم العثور على تكوين المشغل")
                        break
                    except json.JSONDecodeError:
                        continue
            
            if not player_config:
                logger.error("فشل في العثور على تكوين المشغل")
                return None
            
            # استخراج معلومات التدفق
            streaming_data = player_config.get('streamingData', {})
            if not streaming_data:
                logger.error("لا توجد بيانات تدفق متاحة")
                return None
            
            formats = []
            
            # إضافة التنسيقات العادية
            if 'formats' in streaming_data:
                for fmt in streaming_data['formats']:
                    if 'url' in fmt:
                        formats.append({
                            'itag': fmt.get('itag'),
                            'url': fmt['url'],
                            'quality': fmt.get('quality', 'unknown'),
                            'type': 'video',
                            'ext': self._get_extension_from_mime(fmt.get('mimeType', '')),
                            'filesize': fmt.get('contentLength'),
                            'width': fmt.get('width'),
                            'height': fmt.get('height'),
                            'fps': fmt.get('fps'),
                            'vcodec': self._extract_codec(fmt.get('mimeType', ''), 'video'),
                            'acodec': self._extract_codec(fmt.get('mimeType', ''), 'audio')
                        })
            
            # إضافة التنسيقات التكيفية
            if 'adaptiveFormats' in streaming_data:
                for fmt in streaming_data['adaptiveFormats']:
                    if 'url' in fmt:
                        mime_type = fmt.get('mimeType', '')
                        is_video = 'video/' in mime_type
                        is_audio = 'audio/' in mime_type
                        
                        formats.append({
                            'itag': fmt.get('itag'),
                            'url': fmt['url'],
                            'quality': fmt.get('qualityLabel', fmt.get('quality', 'unknown')),
                            'type': 'video' if is_video else 'audio',
                            'ext': self._get_extension_from_mime(mime_type),
                            'filesize': fmt.get('contentLength'),
                            'width': fmt.get('width'),
                            'height': fmt.get('height'),
                            'fps': fmt.get('fps'),
                            'abr': fmt.get('averageBitrate'),
                            'vcodec': self._extract_codec(mime_type, 'video') if is_video else 'none',
                            'acodec': self._extract_codec(mime_type, 'audio') if is_audio else 'none'
                        })
            
            if not formats:
                logger.error("لم يتم العثور على أي تنسيقات للتحميل")
                return None
            
            logger.info(f"تم العثور على {len(formats)} تنسيق للتحميل")
            return {'formats': formats}
            
        except Exception as e:
            logger.error(f"خطأ في استخراج روابط التحميل: {e}")
            return None
    
    def _get_extension_from_mime(self, mime_type: str) -> str:
        """استخراج امتداد الملف من نوع MIME"""
        mime_map = {
            'video/mp4': 'mp4',
            'video/webm': 'webm',
            'audio/mp4': 'm4a',
            'audio/webm': 'webm',
            'audio/mpeg': 'mp3'
        }
        
        for mime, ext in mime_map.items():
            if mime in mime_type:
                return ext
        
        return 'unknown'
    
    def _extract_codec(self, mime_type: str, codec_type: str) -> str:
        """استخراج معلومات الترميز من نوع MIME"""
        if not mime_type:
            return 'unknown'
        
        # البحث عن معلومات الترميز في MIME type
        codec_match = re.search(r'codecs="([^"]+)"', mime_type)
        if not codec_match:
            return 'unknown'
        
        codecs = codec_match.group(1).split(', ')
        
        if codec_type == 'video':
            video_codecs = ['avc1', 'vp9', 'vp8', 'av01']
            for codec in codecs:
                for vc in video_codecs:
                    if codec.startswith(vc):
                        return codec
        elif codec_type == 'audio':
            audio_codecs = ['mp4a', 'opus', 'vorbis']
            for codec in codecs:
                for ac in audio_codecs:
                    if codec.startswith(ac):
                        return codec
        
        return 'unknown'
    
    async def get_complete_video_info(self, video_id: str) -> Optional[Dict]:
        """الحصول على معلومات الفيديو الكاملة مع الروابط باستخدام regex وHTML فقط"""
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
            
            if response.status_code != 200:
                logger.error(f"فشل في الحصول على صفحة الفيديو: {response.status_code}")
                return {'error': 'http_error', 'message': f'HTTP {response.status_code}'}
            
            html = response.text
            
            # فحص إذا كان الفيديو متاحاً
            if 'Video unavailable' in html or 'This video is not available' in html:
                return {'error': 'unavailable', 'message': 'الفيديو غير متاح'}
            
            if 'Private video' in html or 'This video is private' in html:
                return {'error': 'private', 'message': 'الفيديو خاص'}
            
            # استخراج المعلومات الأساسية
            video_info = {
                'id': video_id,
                'webpage_url': url,
                'method': 'regex_html'
            }
            
            # استخراج العنوان
            title_patterns = [
                r'<title>(.+?) - YouTube</title>',
                r'"title":"([^"]+)"',
                r'<meta name="title" content="([^"]+)"',
                r'<meta property="og:title" content="([^"]+)"'
            ]
            
            for pattern in title_patterns:
                match = re.search(pattern, html)
                if match:
                    title = match.group(1).replace('\\u0026', '&').replace('\\', '')
                    video_info['title'] = title
                    break
            
            if 'title' not in video_info:
                video_info['title'] = 'عنوان غير معروف'
            
            # استخراج اسم القناة
            channel_patterns = [
                r'"ownerChannelName":"([^"]+)"',
                r'"author":"([^"]+)"',
                r'<link itemprop="name" content="([^"]+)"',
                r'"channelName":"([^"]+)"'
            ]
            
            for pattern in channel_patterns:
                match = re.search(pattern, html)
                if match:
                    uploader = match.group(1).replace('\\u0026', '&').replace('\\', '')
                    video_info['uploader'] = uploader
                    break
            
            if 'uploader' not in video_info:
                video_info['uploader'] = 'قناة غير معروفة'
            
            # استخراج المدة
            duration_patterns = [
                r'"lengthSeconds":"(\d+)"',
                r'"duration":"PT(\d+)M(\d+)S"',
                r'<meta itemprop="duration" content="PT(\d+)M(\d+)S"'
            ]
            
            duration = 0
            for pattern in duration_patterns:
                match = re.search(pattern, html)
                if match:
                    if 'lengthSeconds' in pattern:
                        duration = int(match.group(1))
                    else:
                        minutes = int(match.group(1))
                        seconds = int(match.group(2))
                        duration = minutes * 60 + seconds
                    break
            
            video_info['duration'] = duration
            
            # استخراج الصورة المصغرة
            thumbnail_patterns = [
                r'"url":"(https://i\.ytimg\.com/vi/[^/]+/maxresdefault\.jpg)"',
                r'"url":"(https://i\.ytimg\.com/vi/[^/]+/hqdefault\.jpg)"',
                r'<meta property="og:image" content="([^"]+)"'
            ]
            
            for pattern in thumbnail_patterns:
                match = re.search(pattern, html)
                if match:
                    thumbnail = match.group(1).replace('\\', '')
                    video_info['thumbnail'] = thumbnail
                    break
            
            if 'thumbnail' not in video_info:
                video_info['thumbnail'] = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            
            # استخراج روابط التحميل
            formats = await self.extract_formats_from_html(html, video_id)
            if formats:
                video_info['formats'] = formats
                logger.info(f"تم استخراج {len(formats)} تنسيق للتحميل")
            else:
                logger.warning("لم يتم العثور على روابط تحميل، جاري المحاولة بطرق بديلة...")
                
                # محاولة استخراج روابط بطريقة مختلفة
                alternative_formats = await self.extract_alternative_formats(html, video_id)
                if alternative_formats:
                    video_info['formats'] = alternative_formats
                    logger.info(f"تم استخراج {len(alternative_formats)} تنسيق بالطريقة البديلة")
                else:
                    logger.error("فشل في استخراج أي روابط تحميل")
                    # لا نرجع خطأ، بل نعطي خيارات افتراضية
                    video_info['formats'] = []
                    video_info['no_direct_download'] = True
            
            return video_info
            
        except Exception as e:
            logger.error(f"خطأ في get_complete_video_info: {e}")
            return {'error': 'extraction_error', 'message': str(e)}
    
    async def extract_formats_from_html(self, html: str, video_id: str) -> List[Dict]:
        """استخراج تنسيقات التحميل من HTML"""
        try:
            formats = []
            
            # البحث عن بيانات التكوين الخاصة بالمشغل
            config_patterns = [
                r'var ytInitialPlayerResponse = ({.+?});',
                r'ytInitialPlayerResponse\s*=\s*({.+?});',
                r'window\["ytInitialPlayerResponse"\]\s*=\s*({.+?});'
            ]
            
            player_config = None
            for pattern in config_patterns:
                matches = re.finditer(pattern, html, re.DOTALL)
                for match in matches:
                    try:
                        config_text = match.group(1)
                        # تنظيف JSON
                        config_text = re.sub(r'\\n', '', config_text)
                        config_text = re.sub(r'\\t', '', config_text)
                        
                        player_config = json.loads(config_text)
                        logger.info("تم العثور على تكوين المشغل بنجاح")
                        break
                    except json.JSONDecodeError as e:
                        logger.warning(f"فشل في تحليل JSON: {e}")
                        continue
                
                if player_config:
                    break
            
            if not player_config:
                logger.error("فشل في العثور على تكوين المشغل")
                return []
            
            # استخراج معلومات التدفق
            streaming_data = player_config.get('streamingData', {})
            if not streaming_data:
                logger.warning("لا توجد streamingData، جاري البحث عن طرق بديلة...")
                
                # محاولة البحث عن بيانات أخرى
                video_details = player_config.get('videoDetails', {})
                if video_details.get('isLiveContent'):
                    logger.error("هذا بث مباشر، غير مدعوم حالياً")
                    return []
                
                # البحث عن بيانات في مواقع أخرى
                microformat = player_config.get('microformat', {}).get('playerMicroformatRenderer', {})
                if microformat:
                    logger.info("تم العثور على microformat، محاولة استخراج بدائل...")
                
                # إذا لم نجد أي بيانات تدفق
                logger.error("لا توجد بيانات تدفق متاحة - قد يكون الفيديو محمياً أو خاص")
                return []
            
            # معالجة التنسيقات العادية
            if 'formats' in streaming_data:
                for fmt in streaming_data['formats']:
                    if 'url' in fmt or 'signatureCipher' in fmt:
                        format_info = self.process_format(fmt, 'video')
                        if format_info:
                            formats.append(format_info)
            
            # معالجة التنسيقات التكيفية
            if 'adaptiveFormats' in streaming_data:
                for fmt in streaming_data['adaptiveFormats']:
                    if 'url' in fmt or 'signatureCipher' in fmt:
                        mime_type = fmt.get('mimeType', '')
                        format_type = 'video' if 'video/' in mime_type else 'audio'
                        format_info = self.process_format(fmt, format_type)
                        if format_info:
                            formats.append(format_info)
            
            # ترتيب التنسيقات حسب الجودة
            video_formats = [f for f in formats if f.get('type') == 'video']
            audio_formats = [f for f in formats if f.get('type') == 'audio']
            
            # ترتيب الفيديو حسب الارتفاع
            video_formats.sort(key=lambda x: x.get('height', 0), reverse=True)
            # ترتيب الصوت حسب البت ريت
            audio_formats.sort(key=lambda x: x.get('abr', 0), reverse=True)
            
            return video_formats + audio_formats
            
        except Exception as e:
            logger.error(f"خطأ في استخراج التنسيقات: {e}")
            return []
    
    def process_format(self, fmt: Dict, format_type: str) -> Optional[Dict]:
        """معالجة تنسيق واحد"""
        try:
            # الحصول على الرابط
            url = fmt.get('url')
            if not url and 'signatureCipher' in fmt:
                # معالجة التواقيع المشفرة (معقدة، قد نحتاج لتجاهلها)
                logger.warning("تم تجاهل تنسيق مشفر")
                return None
            
            if not url:
                return None
            
            mime_type = fmt.get('mimeType', '')
            
            format_info = {
                'itag': fmt.get('itag'),
                'url': url,
                'type': format_type,
                'ext': self._get_extension_from_mime(mime_type),
                'filesize': fmt.get('contentLength'),
                'mime_type': mime_type
            }
            
            if format_type == 'video':
                format_info.update({
                    'width': fmt.get('width'),
                    'height': fmt.get('height'),
                    'fps': fmt.get('fps'),
                    'quality': fmt.get('qualityLabel', f"{fmt.get('height', 'unknown')}p"),
                    'vcodec': self._extract_codec(mime_type, 'video'),
                    'acodec': self._extract_codec(mime_type, 'audio') if 'audio/' not in mime_type else 'none'
                })
            elif format_type == 'audio':
                format_info.update({
                    'abr': fmt.get('averageBitrate', fmt.get('bitrate')),
                    'asr': fmt.get('audioSampleRate'),
                    'quality': f"{fmt.get('averageBitrate', 'unknown')} kbps",
                    'vcodec': 'none',
                    'acodec': self._extract_codec(mime_type, 'audio')
                })
            
            return format_info
            
        except Exception as e:
            logger.error(f"خطأ في معالجة التنسيق: {e}")
            return None
    
    async def extract_alternative_formats(self, html: str, video_id: str) -> List[Dict]:
        """طريقة بديلة لاستخراج التنسيقات عند فشل الطريقة الأساسية"""
        try:
            formats = []
            
            # البحث عن patterns مختلفة في HTML
            alternative_patterns = [
                r'"url":"([^"]+)".*?"itag":(\d+)',
                r'"signatureCipher":"([^"]+)".*?"itag":(\d+)',
                r'itag=(\d+).*?url=([^&]+)',
            ]
            
            for pattern in alternative_patterns:
                matches = re.finditer(pattern, html)
                for match in matches:
                    try:
                        if len(match.groups()) >= 2:
                            url = match.group(1) if 'url' in pattern else match.group(2)
                            itag = match.group(2) if 'url' in pattern else match.group(1)
                            
                            # تنظيف URL
                            if url.startswith('\\'):
                                url = url.replace('\\', '')
                            
                            # إنشاء تنسيق أساسي
                            format_info = {
                                'itag': int(itag) if itag.isdigit() else 0,
                                'url': url,
                                'ext': 'mp4',  # افتراضي
                                'type': 'video'  # افتراضي
                            }
                            
                            # تخمين الجودة بناءً على itag
                            quality_map = {
                                22: {'height': 720, 'quality': '720p'},
                                18: {'height': 360, 'quality': '360p'},
                                140: {'type': 'audio', 'quality': '128kbps', 'ext': 'm4a'},
                                251: {'type': 'audio', 'quality': '160kbps', 'ext': 'webm'},
                            }
                            
                            if int(itag) in quality_map:
                                format_info.update(quality_map[int(itag)])
                            
                            formats.append(format_info)
                    except Exception as e:
                        logger.warning(f"تجاهل تنسيق غير صحيح: {e}")
                        continue
            
            # إزالة التكرارات
            unique_formats = []
            seen_itags = set()
            for fmt in formats:
                if fmt['itag'] not in seen_itags:
                    unique_formats.append(fmt)
                    seen_itags.add(fmt['itag'])
            
            logger.info(f"تم استخراج {len(unique_formats)} تنسيق بالطريقة البديلة")
            return unique_formats
            
        except Exception as e:
            logger.error(f"خطأ في الطريقة البديلة: {e}")
            return []
    
    async def create_fallback_formats(self, video_id: str) -> List[Dict]:
        """إنشاء تنسيقات افتراضية عند فشل جميع الطرق"""
        try:
            # تنسيقات يوتيوب الشائعة
            common_formats = [
                {
                    'itag': 22,
                    'url': f'https://www.youtube.com/watch?v={video_id}',  # رابط وهمي
                    'quality': '720p',
                    'height': 720,
                    'ext': 'mp4',
                    'type': 'video',
                    'fallback': True
                },
                {
                    'itag': 18,
                    'url': f'https://www.youtube.com/watch?v={video_id}',  # رابط وهمي
                    'quality': '360p', 
                    'height': 360,
                    'ext': 'mp4',
                    'type': 'video',
                    'fallback': True
                },
                {
                    'itag': 140,
                    'url': f'https://www.youtube.com/watch?v={video_id}',  # رابط وهمي
                    'quality': '128kbps',
                    'ext': 'm4a',
                    'type': 'audio',
                    'fallback': True
                }
            ]
            
            return common_formats
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء التنسيقات الافتراضية: {e}")
            return []
        
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
            # اختبار النظام الجديد
            result = await self.get_complete_video_info(video_id)
            
            if result and 'title' in result and 'error' not in result:
                method = result.get('method', 'غير معروف')
                title = result.get('title', 'غير معروف')
                uploader = result.get('uploader', 'غير معروف')
                duration = self.format_duration(result.get('duration', 0))
                formats_count = len(result.get('formats', []))
                
                success_msg = f"""
✅ **نجح الاختبار!**

🎬 **العنوان:** {title[:50]}
👤 **القناة:** {uploader}
⏱️ **المدة:** {duration}
🔧 **الطريقة:** {method}
📊 **التنسيقات المتاحة:** {formats_count}

💡 النظام الجديد يعمل بنجاح بدون yt-dlp!
                """
                
                await test_message.edit_text(success_msg, parse_mode=ParseMode.MARKDOWN)
            else:
                error_msg = result.get('message', 'خطأ غير معروف') if result else 'فشل في الاستخراج'
                await test_message.edit_text(
                    f"❌ فشل في الاختبار\n"
                    f"**السبب:** {error_msg}"
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



    async def get_video_info(self, url: str) -> Optional[Dict]:
        """الحصول على معلومات الفيديو باستخدام regex وتحليل HTML فقط"""
        
        # استخراج معرف الفيديو
        video_id = self.extract_video_id(url)
        if not video_id:
            logger.error("فشل في استخراج معرف الفيديو من الرابط")
            return {'error': 'invalid_url', 'message': 'رابط غير صحيح'}
        
        logger.info(f"جاري تحليل الفيديو: {video_id}")
        
        # الحصول على معلومات الفيديو والروابط في عملية واحدة
        video_info = await self.get_complete_video_info(video_id)
        
        if not video_info:
            return {'error': 'extraction_failed', 'message': 'فشل في استخراج معلومات الفيديو'}
        
        if 'error' in video_info:
            return video_info
        
        logger.info(f"تم استخراج معلومات الفيديو بنجاح: {video_info.get('title', 'غير معروف')[:30]}...")
        return video_info

    def create_quality_keyboard(self, video_info: Dict) -> InlineKeyboardMarkup:
        """إنشاء لوحة مفاتيح اختيار الجودة"""
        keyboard = []
        
        # جودات الفيديو المتاحة
        formats = video_info.get('formats', [])
        video_formats = {}
        audio_formats = []
        
        # تصنيف التنسيقات
        for fmt in formats:
            if fmt.get('type') == 'video' and fmt.get('height'):
                height = fmt.get('height')
                if height not in video_formats:
                    video_formats[height] = fmt
                elif fmt.get('filesize', 0) > video_formats[height].get('filesize', 0):
                    video_formats[height] = fmt
            elif fmt.get('type') == 'audio' or (fmt.get('vcodec') == 'none' and fmt.get('acodec') != 'none'):
                audio_formats.append(fmt)
        
        # إذا لم توجد تنسيقات من الطرق البديلة، استخدم التنسيق التقليدي
        if not video_formats and not audio_formats:
            # استخدام التنسيق القديم مع yt-dlp
            for fmt in formats:
                if fmt.get('vcodec') != 'none' and fmt.get('height'):
                    height = fmt.get('height')
                    if height not in video_formats or fmt.get('filesize', 0) > video_formats[height].get('filesize', 0):
                        video_formats[height] = fmt
        
        # ترتيب الجودات من الأعلى للأقل
        sorted_qualities = sorted(video_formats.keys(), reverse=True) if video_formats else []
        
        # إضافة أزرار الجودة
        for quality in sorted_qualities[:6]:  # أول 6 جودات
            quality_text = f"📹 {quality}p"
            callback_data = f"video_{quality}"
            keyboard.append([InlineKeyboardButton(quality_text, callback_data=callback_data)])
        
        # إذا لم توجد جودات فيديو، أضف خيارات عامة
        if not sorted_qualities:
            if video_info.get('no_direct_download'):
                # إذا لم نستطع الحصول على روابط مباشرة
                keyboard.extend([
                    [InlineKeyboardButton("📹 محاولة تحميل جودة عالية", callback_data="video_720")],
                    [InlineKeyboardButton("📹 محاولة تحميل جودة متوسطة", callback_data="video_480")],
                    [InlineKeyboardButton("🎵 محاولة تحميل الصوت", callback_data="audio_mp3")]
                ])
                
                # إضافة تحذير
                keyboard.append([InlineKeyboardButton("⚠️ قد لا يعمل التحميل المباشر", callback_data="warning")])
            else:
                keyboard.extend([
                    [InlineKeyboardButton("📹 جودة عالية", callback_data="video_720")],
                    [InlineKeyboardButton("📹 جودة متوسطة", callback_data="video_480")],
                    [InlineKeyboardButton("📹 جودة منخفضة", callback_data="video_360")]
                ])
        
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
        
        if data == "warning":
            await query.answer(
                "⚠️ لم نتمكن من الحصول على روابط تحميل مباشرة لهذا الفيديو. "
                "قد يكون الفيديو محمياً أو يتطلب معالجة خاصة. "
                "يمكنك المحاولة لكن قد لا يعمل التحميل.",
                show_alert=True
            )
            return
        
        session = self.user_sessions[user_id]
        
        # إنشاء callback لتحديث التقدم
        async def progress_callback(message: str):
            try:
                await query.edit_message_text(message)
            except Exception as e:
                # تجاهل أخطاء التحديث السريع للرسائل
                if "message is not modified" not in str(e).lower():
                    logger.warning(f"خطأ في تحديث رسالة التقدم: {e}")
        
        # إضافة callback للجلسة
        session['progress_callback'] = progress_callback
        
        # رسالة البداية
        await progress_callback("⬇️ جاري التحضير للتحميل...")
        
        try:
            if data.startswith("video_"):
                quality = data.split("_")[1]
                file_path = await self.download_video_with_fallback(session, quality)
            elif data.startswith("audio_"):
                file_path = await self.download_audio_with_fallback(session)
            else:
                await query.edit_message_text("❌ خيار غير صحيح!")
                return
            
            if file_path and os.path.exists(file_path):
                # تحديث الرسالة قبل الإرسال
                await progress_callback("📤 جاري إرسال الملف...")
                
                # إرسال الملف
                await self.send_file(query, file_path)
                
                # حذف الملف بعد الإرسال
                os.remove(file_path)
            else:
                # رسائل خطأ محسنة
                video_info = session.get('video_info', {})
                if video_info.get('no_direct_download'):
                    await query.edit_message_text(
                        "❌ **فشل في التحميل**\n\n"
                        "🔒 هذا الفيديو محمي أو يتطلب معالجة خاصة.\n"
                        "💡 **جرب:**\n"
                        "• فيديو آخر من نفس القناة\n"
                        "• استخدام VPN إذا كان متاحاً\n"
                        "• المحاولة لاحقاً",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await query.edit_message_text(
                        "❌ **فشل في تحميل الملف**\n\n"
                        "💡 **الأسباب المحتملة:**\n"
                        "• مشكلة مؤقتة في الخادم\n"
                        "• انتهاء صلاحية الرابط\n"
                        "• مشكلة في الاتصال\n\n"
                        "🔄 جرب إعادة إرسال الرابط",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
        except Exception as e:
            logger.error(f"خطأ في التحميل: {e}")
            await query.edit_message_text("❌ حدث خطأ أثناء التحميل!")
        
        finally:
            # تنظيف الجلسة
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]



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
    
    def create_progress_bar(self, percentage: float, length: int = 10) -> str:
        """إنشاء شريط تقدم مرئي"""
        filled_length = int(length * percentage / 100)
        bar = '█' * filled_length + '░' * (length - filled_length)
        return f"[{bar}]"
    
    async def download_video_with_fallback(self, session: Dict, quality: str) -> Optional[str]:
        """تحميل الفيديو باستخدام الروابط المستخرجة بـ regex فقط"""
        video_info = session.get('video_info', {})
        
        if 'formats' not in video_info or not video_info['formats']:
            if video_info.get('no_direct_download'):
                logger.warning("لا توجد روابط مباشرة، محاولة إنشاء تنسيقات افتراضية...")
                fallback_formats = await self.create_fallback_formats(video_info.get('id', ''))
                if fallback_formats:
                    video_info['formats'] = fallback_formats
                    logger.info("تم إنشاء تنسيقات افتراضية")
                else:
                    logger.error("فشل في إنشاء تنسيقات افتراضية")
                    return None
            else:
                logger.error("لا توجد تنسيقات متاحة للتحميل")
                return None
        
        logger.info("جاري التحميل المباشر باستخدام الروابط المستخرجة...")
        
        # إنشاء callback للتقدم إذا كان متاحاً
        progress_callback = getattr(session, 'progress_callback', None)
        return await self.download_direct_video(video_info, quality, progress_callback)
    
    async def download_audio_with_fallback(self, session: Dict) -> Optional[str]:
        """تحميل الصوت باستخدام الروابط المستخرجة بـ regex فقط"""
        video_info = session.get('video_info', {})
        
        if 'formats' not in video_info or not video_info['formats']:
            if video_info.get('no_direct_download'):
                logger.warning("لا توجد روابط مباشرة، محاولة إنشاء تنسيقات افتراضية...")
                fallback_formats = await self.create_fallback_formats(video_info.get('id', ''))
                if fallback_formats:
                    video_info['formats'] = fallback_formats
                    logger.info("تم إنشاء تنسيقات افتراضية")
                else:
                    logger.error("فشل في إنشاء تنسيقات افتراضية")
                    return None
            else:
                logger.error("لا توجد تنسيقات متاحة للتحميل")
                return None
        
        logger.info("جاري تحميل الصوت المباشر باستخدام الروابط المستخرجة...")
        
        # إنشاء callback للتقدم إذا كان متاحاً
        progress_callback = getattr(session, 'progress_callback', None)
        return await self.download_direct_audio(video_info, progress_callback)
    
    async def download_direct_video(self, video_info: Dict, quality: str, progress_callback=None) -> Optional[str]:
        """تحميل الفيديو مباشرة من الروابط المستخرجة مع شريط التقدم"""
        try:
            formats = video_info.get('formats', [])
            target_quality = int(quality)
            
            # البحث عن أفضل تنسيق فيديو
            best_format = None
            best_score = -1
            
            for fmt in formats:
                if fmt.get('type') == 'video' and fmt.get('height'):
                    height = fmt.get('height')
                    # حساب نقاط الجودة (كلما قرب من الجودة المطلوبة كان أفضل)
                    score = 1000 - abs(height - target_quality)
                    
                    # إضافة نقاط إضافية للتنسيقات الأفضل
                    if fmt.get('ext') == 'mp4':
                        score += 100
                    
                    if score > best_score:
                        best_score = score
                        best_format = fmt
            
            if not best_format:
                logger.error("لم يتم العثور على تنسيق فيديو مناسب")
                return None
            
            # التحقق من التنسيقات الافتراضية
            if best_format.get('fallback'):
                logger.warning("استخدام تنسيق افتراضي - قد لا يعمل التحميل")
                return None
            
            # تحميل الملف مع شريط التقدم
            download_url = best_format['url']
            filename = f"video_{quality}p_{video_info.get('id', 'unknown')}.{best_format.get('ext', 'mp4')}"
            file_path = os.path.join(DOWNLOAD_PATH, filename)
            
            logger.info(f"جاري تحميل الفيديو من: {download_url[:50]}...")
            
            if progress_callback:
                await progress_callback("🔗 الاتصال بالخادم...")
            
            proxies = {'http': PROXY_URL, 'https': PROXY_URL} if USE_PROXY and PROXY_URL else None
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            
            response = await asyncio.to_thread(
                requests.get, download_url,
                proxies=proxies,
                headers=headers,
                stream=True,
                timeout=30
            )
            
            if response.status_code == 200:
                # الحصول على حجم الملف
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                
                if progress_callback:
                    size_mb = total_size / (1024 * 1024) if total_size > 0 else 0
                    await progress_callback(f"📥 بدء التحميل... ({size_mb:.1f} MB)")
                
                with open(file_path, 'wb') as f:
                    chunk_count = 0
                    start_time = time.time()
                    last_update_time = start_time
                    last_downloaded_size = 0
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            chunk_count += 1
                            
                            current_time = time.time()
                            
                            # تحديث التقدم كل 100 chunk أو كل 2 ثانية (حوالي 800KB)
                            if progress_callback and (chunk_count % 100 == 0 or (current_time - last_update_time) >= 2) and total_size > 0:
                                progress_percent = (downloaded_size / total_size) * 100
                                downloaded_mb = downloaded_size / (1024 * 1024)
                                total_mb = total_size / (1024 * 1024)
                                
                                # حساب سرعة التحميل
                                elapsed_time = current_time - last_update_time
                                if elapsed_time > 0:
                                    speed_bytes = (downloaded_size - last_downloaded_size) / elapsed_time
                                    speed_mb = speed_bytes / (1024 * 1024)
                                    
                                    # تقدير الوقت المتبقي
                                    remaining_bytes = total_size - downloaded_size
                                    eta_seconds = remaining_bytes / speed_bytes if speed_bytes > 0 else 0
                                    eta_minutes = eta_seconds / 60
                                    
                                    # إنشاء شريط التقدم
                                    progress_bar = self.create_progress_bar(progress_percent)
                                    
                                    eta_text = f"⏱️ {eta_minutes:.1f} دقيقة متبقية" if eta_minutes > 1 else f"⏱️ {eta_seconds:.0f} ثانية متبقية"
                                    
                                    await progress_callback(
                                        f"📥 جاري التحميل...\n"
                                        f"{progress_bar} {progress_percent:.1f}%\n"
                                        f"📊 {downloaded_mb:.1f} MB / {total_mb:.1f} MB\n"
                                        f"🚀 {speed_mb:.1f} MB/s\n"
                                        f"{eta_text}"
                                    )
                                    
                                    last_update_time = current_time
                                    last_downloaded_size = downloaded_size
                
                if progress_callback:
                    final_size_mb = downloaded_size / (1024 * 1024)
                    await progress_callback(f"✅ تم التحميل بنجاح! ({final_size_mb:.1f} MB)")
                
                logger.info(f"تم تحميل الفيديو بنجاح: {file_path}")
                return file_path
            else:
                logger.error(f"فشل في تحميل الفيديو: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"خطأ في التحميل المباشر للفيديو: {e}")
            if progress_callback:
                await progress_callback(f"❌ خطأ في التحميل: {str(e)[:50]}...")
            return None
    
    async def download_direct_audio(self, video_info: Dict, progress_callback=None) -> Optional[str]:
        """تحميل الصوت مباشرة من الروابط المستخرجة مع شريط التقدم"""
        try:
            formats = video_info.get('formats', [])
            
            # البحث عن أفضل تنسيق صوتي
            best_format = None
            best_score = -1
            
            for fmt in formats:
                if fmt.get('type') == 'audio' or (fmt.get('vcodec') == 'none' and fmt.get('acodec') != 'none'):
                    score = 0
                    
                    # تفضيل التنسيقات الأفضل
                    if fmt.get('ext') in ['m4a', 'mp3']:
                        score += 100
                    
                    # تفضيل البت ريت الأعلى
                    if fmt.get('abr'):
                        score += fmt.get('abr', 0)
                    
                    if score > best_score:
                        best_score = score
                        best_format = fmt
            
            if not best_format:
                logger.error("لم يتم العثور على تنسيق صوتي مناسب")
                return None
            
            # التحقق من التنسيقات الافتراضية
            if best_format.get('fallback'):
                logger.warning("استخدام تنسيق افتراضي - قد لا يعمل التحميل")
                return None
            
            # تحميل الملف مع شريط التقدم
            download_url = best_format['url']
            filename = f"audio_{video_info.get('id', 'unknown')}.{best_format.get('ext', 'm4a')}"
            file_path = os.path.join(DOWNLOAD_PATH, filename)
            
            logger.info(f"جاري تحميل الصوت من: {download_url[:50]}...")
            
            if progress_callback:
                await progress_callback("🔗 الاتصال بالخادم...")
            
            proxies = {'http': PROXY_URL, 'https': PROXY_URL} if USE_PROXY and PROXY_URL else None
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            
            response = await asyncio.to_thread(
                requests.get, download_url,
                proxies=proxies,
                headers=headers,
                stream=True,
                timeout=30
            )
            
            if response.status_code == 200:
                # الحصول على حجم الملف
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                
                if progress_callback:
                    size_mb = total_size / (1024 * 1024) if total_size > 0 else 0
                    await progress_callback(f"🎵 بدء تحميل الصوت... ({size_mb:.1f} MB)")
                
                with open(file_path, 'wb') as f:
                    chunk_count = 0
                    start_time = time.time()
                    last_update_time = start_time
                    last_downloaded_size = 0
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            chunk_count += 1
                            
                            current_time = time.time()
                            
                            # تحديث التقدم كل 50 chunk أو كل 1.5 ثانية للصوت
                            if progress_callback and (chunk_count % 50 == 0 or (current_time - last_update_time) >= 1.5) and total_size > 0:
                                progress_percent = (downloaded_size / total_size) * 100
                                downloaded_mb = downloaded_size / (1024 * 1024)
                                total_mb = total_size / (1024 * 1024)
                                
                                # حساب سرعة التحميل
                                elapsed_time = current_time - last_update_time
                                if elapsed_time > 0:
                                    speed_bytes = (downloaded_size - last_downloaded_size) / elapsed_time
                                    speed_mb = speed_bytes / (1024 * 1024)
                                    
                                    # تقدير الوقت المتبقي
                                    remaining_bytes = total_size - downloaded_size
                                    eta_seconds = remaining_bytes / speed_bytes if speed_bytes > 0 else 0
                                    
                                    # إنشاء شريط التقدم
                                    progress_bar = self.create_progress_bar(progress_percent)
                                    
                                    eta_text = f"⏱️ {eta_seconds:.0f} ثانية متبقية" if eta_seconds > 0 else "⏱️ اكتمل تقريباً"
                                    
                                    await progress_callback(
                                        f"🎵 جاري تحميل الصوت...\n"
                                        f"{progress_bar} {progress_percent:.1f}%\n"
                                        f"📊 {downloaded_mb:.1f} MB / {total_mb:.1f} MB\n"
                                        f"🚀 {speed_mb:.1f} MB/s\n"
                                        f"{eta_text}"
                                    )
                                    
                                    last_update_time = current_time
                                    last_downloaded_size = downloaded_size
                
                if progress_callback:
                    final_size_mb = downloaded_size / (1024 * 1024)
                    await progress_callback(f"✅ تم تحميل الصوت بنجاح! ({final_size_mb:.1f} MB)")
                
                logger.info(f"تم تحميل الصوت بنجاح: {file_path}")
                return file_path
            else:
                logger.error(f"فشل في تحميل الصوت: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"خطأ في التحميل المباشر للصوت: {e}")
            if progress_callback:
                await progress_callback(f"❌ خطأ في تحميل الصوت: {str(e)[:50]}...")
            return None

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

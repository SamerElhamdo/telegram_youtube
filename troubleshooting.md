# 🛠️ دليل استكشاف الأخطاء وحلولها

## 🚨 الأخطاء الشائعة وحلولها

### 1. 🌍 خطأ: "الفيديو غير متاح في بلدك"
```
ERROR: [youtube] Video unavailable. The uploader has not made this video available in your country
```

**الحلول:**

#### أ) استخدام VPN
```bash
# تثبيت VPN مجاني مثل ProtonVPN أو Windscribe
# ثم اتصل بخادم في بلد مختلف
```

#### ب) استخدام البروكسي
1. **إعداد البروكسي في الملف `.env`:**
```env
USE_PROXY=true
PROXY_URL=http://your-proxy-server:port
```

2. **أمثلة على البروكسي المجاني:**
```env
# بروكسي HTTP
PROXY_URL=http://free-proxy.cz:8080

# بروكسي SOCKS5
PROXY_URL=socks5://127.0.0.1:1080
```

#### ج) استخدام Tor (متقدم)
```bash
# تثبيت Tor
brew install tor  # macOS
sudo apt install tor  # Ubuntu

# تشغيل Tor
tor

# في ملف .env
USE_PROXY=true
PROXY_URL=socks5://127.0.0.1:9050
```

### 2. 🔒 خطأ: "يوتيوب يطلب تسجيل الدخول"
```
ERROR: Sign in to confirm you're not a bot
```

**الحلول:**

#### أ) انتظار وإعادة المحاولة
- انتظر 10-15 دقيقة
- جرب فيديو مختلف
- أعد تشغيل البوت

#### ب) تغيير User Agent
البوت يستخدم User Agents عشوائية تلقائياً، لكن يمكنك إضافة المزيد:

```python
# في ملف bot.py، أضف المزيد إلى قائمة USER_AGENTS
USER_AGENTS.extend([
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15',
    'Mozilla/5.0 (Android 11; Mobile; rv:89.0) Gecko/89.0 Firefox/89.0'
])
```

#### ج) استخدام البروكسي
```env
USE_PROXY=true
PROXY_URL=your_proxy_here
```

### 3. ❌ خطأ: "الفيديو غير متاح"
```
ERROR: Video unavailable
```

**الأسباب المحتملة:**
- الفيديو محذوف
- الفيديو خاص
- القناة معلقة
- مشكلة مؤقتة

**الحلول:**
- تأكد من صحة الرابط
- جرب فيديو آخر من نفس القناة
- انتظر وحاول لاحقاً

### 4. 🔧 خطأ: "FFmpeg not found"
```
ERROR: ffmpeg not found
```

**الحلول:**

#### macOS:
```bash
brew install ffmpeg
```

#### Ubuntu/Debian:
```bash
sudo apt update
sudo apt install ffmpeg
```

#### Windows:
1. حمل FFmpeg من [الموقع الرسمي](https://ffmpeg.org/download.html)
2. فك الضغط في مجلد `C:\ffmpeg`
3. أضف `C:\ffmpeg\bin` إلى PATH

### 5. 💾 خطأ: "File too large"
```
File size exceeds Telegram limit (50MB)
```

**الحلول:**
- اختر جودة أقل (480p بدلاً من 1080p)
- استخدم خيار "صوت فقط"
- البوت سيرفض الملفات الكبيرة تلقائياً

### 6. 🚫 خطأ: "Invalid token"
```
ERROR: Invalid token
```

**الحلول:**
1. تأكد من صحة token البوت في `.env`
2. تأكد من عدم وجود مسافات إضافية
3. احصل على token جديد من @BotFather

## 🔧 إعدادات متقدمة لحل المشاكل

### 1. تحديث yt-dlp
```bash
pip install --upgrade yt-dlp
```

### 2. مسح الكاش
```bash
rm -rf ~/.cache/yt-dlp/
```

### 3. تشغيل البوت مع تفاصيل أكثر
```python
# في ملف bot.py، غير مستوى التسجيل
logging.basicConfig(level=logging.DEBUG)
```

### 4. اختبار الاتصال بيوتيوب
```bash
# اختبار بسيط
yt-dlp --list-formats "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## 🌐 قائمة بروكسيات مجانية موثوقة

### HTTP Proxies:
```
http://free-proxy.cz:8080
http://proxy-list.org:8080
http://spys.one:8080
```

### SOCKS5 Proxies:
```
socks5://free-proxy.cz:1080
socks5://proxy-list.org:1080
```

**تحذير:** البروكسيات المجانية قد تكون بطيئة أو غير موثوقة. للاستخدام المكثف، فكر في بروكسي مدفوع.

## 📊 مراقبة الأداء

### 1. فحص استخدام الذاكرة
```bash
ps aux | grep python
```

### 2. فحص مساحة القرص
```bash
du -sh downloads/
```

### 3. تنظيف الملفات المؤقتة
```bash
# إنشاء سكريبت تنظيف
cat > cleanup.sh << 'EOF'
#!/bin/bash
find downloads/ -type f -mtime +1 -delete
echo "تم تنظيف الملفات القديمة"
EOF

chmod +x cleanup.sh
./cleanup.sh
```

## 🔄 إعادة تشغيل تلقائية

### استخدام systemd (Linux):
```bash
# إنشاء ملف الخدمة
sudo nano /etc/systemd/system/telegram-bot.service
```

```ini
[Unit]
Description=Telegram YouTube Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/telegram_youtube
ExecStart=/path/to/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# تفعيل الخدمة
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
```

## 📞 الحصول على المساعدة

إذا استمرت المشاكل:

1. **تحقق من السجلات:**
   ```bash
   tail -f bot.log
   ```

2. **اجمع معلومات النظام:**
   ```bash
   python --version
   pip list | grep -E "(telegram|yt-dlp)"
   ffmpeg -version
   ```

3. **أنشئ تقرير مشكلة** يتضمن:
   - رسالة الخطأ الكاملة
   - نوع الفيديو الذي تحاول تحميله
   - معلومات النظام
   - الخطوات المتبعة

---

💡 **نصيحة:** احتفظ بنسخة احتياطية من إعداداتك العاملة دائماً!

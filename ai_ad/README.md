# إعلان TikTok عن الذكاء الاصطناعي — "المستقبل مش بيستنى حد"

**المدة:** حوالي 58 ثانية · **المقاس:** 1080×1920 (9:16) · **30fps**

## الفكرة
الإعلان بيبدأ بسؤال يصدم المشاهد: *"إنت لسه فاكر إن الذكاء الاصطناعي حاجة جاية؟"*
وبعدين بيوريه في مشاهد سريعة إن الـAI موجود فعلاً في الطب والهندسة والبيزنس.
بعد كده بيقلب الخوف لفرصة: *"الـAI مش هياخد شغلك… اللي هياخده واحد بيستخدمه أحسن منك"*،
وبيقفل بخطوة عملية سهلة (أداة واحدة كل أسبوع) وCTA للمتابعة.

الهيكل مبني على طريقة الإعلانات اللي بتنجح على تيك توك:
Hook في أول ثانيتين ← إثبات ← صدمة/توتر ← أمل وخطوة عملية ← CTA.

## المشاهد
| # | الصورة | الفويس أوفر | النص على الشاشة | الانتقال |
|---|--------|-------------|------------------|----------|
| 1 | عين بشرية فيها شبكة عصبية مضيئة | إنت لسه فاكر إن الذكاء الاصطناعي حاجة جاية…؟ المستقبل ده بدأ خلاص. | الذكاء الاصطناعي / **بدأ خلاص.** | فتح من الأسود + Boom |
| 2 | موبايل بيطلع منه هولوجرام إبداع | الموبايل اللي في إيدك بقى بيكتب، وبيرسم، وبيترجم، وبيتكلم. | بيكتب · بيرسم · بيترجم · بيتكلم | Zoom Punch |
| 3 | دكتورة قدام سكان هولوجرام | الدكاترة بيكتشفوا الأمراض قبل ما تظهر | يكتشف المرض / **قبل ما يظهر** | Whip Pan |
| 4 | مهندس ومدينة هولوجرام دهبي | والمهندسين بيصمموا مدن كاملة في ساعات بدل سنين. | مدن كاملة / في ساعات / ~~مش سنين~~ | Light Flash |
| 5 | رائد أعمال لوحده بالليل وقدامه القاهرة | وفي ناس بتبني مشاريع كاملة لوحدها… | مشروع كامل / **لوحدك.** | Zoom Punch |
| 6 | إنسان وروبوت وش لوش | الـAI مش هياخد شغلك… اللي هياخده واحد بيستخدمه أحسن منك. | مش هياخد شغلك ← **أحسن منك** | Glitch |
| 7 | شخص قدام بوابة نور | والخبر الحلو؟ إنك لسه في الأول. ابدأ النهارده… | لسه في الأول / ابدأ النهارده | Light Flash |
| 8 | شاب على سطح وقت الشروق فوق القاهرة | وبعد سنة، هتبقى شخص تاني خالص. تابعنا… | شخص تاني خالص / **تابعنا + متابعة** | Iris Reveal |

## الإنتاج
- **الصور:** اتولدت بالذكاء الاصطناعي على Runway بستايل إعلانات تكنولوجيا فاخرة (إضاءة سينمائية، Teal & Orange).
- **الفويس أوفر:** صوت رجالي عربي (Runway TTS)، والسكريبت بيتقسم تلقائي على السكوت بين الجمل ويتوزع على المشاهد.
- **الموسيقى والمؤثرات:** متولدة بالكود — Drone وHeartbeat في البداية، Drop على المشهد 2، Breakdown بساعة بتتك في مشهد التحذير، وختام ملحمي. وفيه Whooshes وBooms وGlitches متزامنة مع الانتقالات، والموسيقى بتوطى تلقائي تحت الصوت (Ducking).
- **الأنيميشن:** Ken Burns لكل صورة، Bloom، Light Leaks، Particles، إطار HUD، Scanline، اهتزاز كاميرا مع الكلمات القوية، كابشن بستايل تيك توك، وشريط تقدم فوق.

## التشغيل
```bash
pip install pillow numpy imageio-ffmpeg
python3 make_ai_ad.py --preview   # out/contact.png
python3 make_ai_ad.py             # out/ai_ad.mp4
```
الصور بتتحط في `assets/img/` بأسماء `01_eye.png … 08_sunrise.png`، والفويس في `assets/vo.mp3`.
لو حاجة منهم ناقصة، السكريبت بيحط بدلها Placeholder عشان تقدر تجرب التوقيتات.

## Prompts الصور
1. Extreme macro close-up of a human eye, the iris reflecting a glowing electric-blue neural network…
2. A hand holding a sleek black smartphone… a floating holographic explosion of glowing creations…
3. A female doctor… studying a large floating holographic human body scan…
4. An architect… a glowing holographic futuristic city assembles itself from golden light particles…
5. A young Arab entrepreneur alone at a minimalist desk at night… Cairo skyline and the Nile lights…
6. Dramatic profile face-off: a human man and a sleek white humanoid AI robot…
7. Silhouette of a young person… at the entrance of a vast glowing portal made of flowing digital light…
8. A confident young Arab man… on a rooftop at golden sunrise overlooking a futuristic Cairo skyline…

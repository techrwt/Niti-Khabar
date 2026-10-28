SAMPLE.JSON KO KAISE SAMAJHEIN (writer ke liye)
================================================

Data/sample.json me 2 poore example articles hain. Ye FILE SIRF NAMUNA hai.
Isse Data/batches/ me MAT daalna, warna demo khabrein live ho jayengi.

Asli kaam: Data/batches/Batch-1.json, Batch-2.json ... banao. Har file ek JSON "array" hai:
[ { article 1 }, { article 2 }, ... ]   (articles ke beech comma, aakhri ke baad comma NAHI)

ZARURI FIELDS (inke bina error aata hai)
-----------------------------------------
title        Khabar ki headline (hindi). Behtar: 70 akshar se kam.
slug         URL ka naam. Sirf chhote english letters, digits aur hyphen (-). Max 80. Har khabar ka alag.
             Jaise: rbi-sgb-redemption
category     config/categories.json me jo slug hai wahi likho. Valid slugs:
             sarkari-khabar, business-news, duniya-khabar, tech-news,
             vigyan-space, swasthya-khabar, mausam-aapda, court-kanoon
summary      2 line ka saar (meta description bhi yahi banta hai). Behtar: 120 se 160 akshar.
body         Poori khabar. Niyam neeche diye hain.
source       Strot ka naam (jaise "भारतीय रिज़र्व बैंक (RBI)")
source_link  Strot ka poora link, https:// se shuru.
image        Image ka sirf NAAM, bina .jpg/.png ke (jaise rbi-sgb-redemption).
             Builder assets/images/ me rbi-sgb-redemption.webp dhoondhta hai.
             Capital/small letters ya space/underscore ka fark apne aap theek ho jata hai.
image_alt    Image ka chhota hindi vivaran (screen reader aur SEO ke liye).
key_points   "Ek nazar me" box ke points. Text ki list: ["point 1", "point 2"]
tags         Text ki list: ["RBI", "सोना"]. Kisi tag par 3 ya zyada khabrein hon to uska tag page bhi ban jata hai.

VAIKALPIK (optional) FIELDS
----------------------------
published      Samay, IST me: "2026-10-27T09:30:00+05:30". Na likho to batch file ke pehle git commit ka samay liya jata hai.
updated        Update ka samay, aise hi format me. Likhoge to khabar par "अपडेट" dikhega.
article_type   "news" (default), "explainer" ya "roundup".
explainer      "Iska matlab kya hai" box ka text (2-3 line).
glossary       Kathin shabdon ki list: [{"term": "शब्द", "meaning": "मतलब"}]
faq            Sawal-jawab: [{"q": "सवाल?", "a": "जवाब"}]
timeline       Ghatnakram: [{"date": "1 अक्टूबर 2026", "event": "क्या हुआ"}]
extra_sources  Aur strot: [{"name": "नाम", "link": "https://..."}]

BODY KAISE LIKHEIN
-------------------
- Paragraphs ke beech ek KHAALI LINE chhodo.
- Line ki shuruaat me "## " lagao to upshirshak (h2) banta hai.
- Line ki shuruaat me "- " lagao to bullet list banti hai.
- Dusri khabar ka link: [[slug|dikhne wala text]]  (slug maujood hona chahiye, warna ERROR).
- HTML tags MAT likho; wo text ki tarah dikh jayenge (warning aayegi).
- JSON ke andar double quote (") likhna ho to \" likho, aur nayi line ke liye \n.

COMMON GALTIYAN
----------------
- Aakhri article ke baad comma lagana ya do articles ke beech comma bhoolna.
- Hindi text me " (double quote) bina \ ke likh dena.
- image ka naam aur assets/images ki file ka naam alag hona.
- Do khabron ka slug same hona.

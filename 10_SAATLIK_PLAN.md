# JARVIS 10 SAATLIK PLAN (4-5 Kasım 2026)

Bu plan, "JARVIS gerçekten istediğim her oyunu yapsın, sıfırdan, en iyisi olsun" hedefinin gerçekçi yoludur.
Dürüst not: hiçbir plan "her şey mükemmel ve bedava" garantisi veremez. Bu plan, üretebildiğimiz en iyisini verir.

## Bölüm 1 — Öncelikler (sırayla yapılır)
1. Oyun uretici sağlamlaştırma (bugün yapıldı: hakem + tarayıcı testi + çoklu varyant).
2. Sıfırdan "bilinmeyen oyun" üretimi: AI'ya oyun tasarımı yaptırıp kodu üretmek (yapıldı, test edildi).
3. Roblox zengin prototip: grafik (Atmosphere/Bloom/DoF/ColorCorrection/Clouds), animasyon (TweenService), parçacıklar (ParticleEmitter) — her oyunda otomatik.
4. Unity oyun üretimi: C# şablonları + proje yapısı + (varsa) EXE üretimi.
5. Klonlama/benzetme: PUBG Mobile, Brawl Stars, Among Us, Minecraft, Candy Crush mekaniği benzeri — AI ile sıfırdan benzer oynanış + tamamen ücretsiz.
6. Hakem sistemi: 3 varyant üret → node ile JS sözdizimi denetle → headless tarayıcıda gerçek test (console hataları, canvas, HUD) → hakem puanlar → en iyisi kazanır (yapıldı, test edildi).
7. 100 AI işçi: proje planı → kod → test → hakem → rapor (çalışıyor, ancak pollinations rate-limit nedeniyle 10-20 dakika sürer).

## Bölüm 2 — Gerçekçi sınırlar (dürüstçe)
- AI sağlayıcıları ücretsiz ve rate-limit uygular (pollinations: her istek ~45 sn bekleme). Bu yüzden 6 saat = 6 saat tam dolu üretim DEĞİL; iş bitene kadar sürer.
- "PUBG Mobile kalitesi" (AAA) mümkün değildir; gerçekten oynanabilir, güzel görselli, tamamen yeni oyunlar üretilebilir.
- Roblox tarafında grafik/animasyon zenginliği Roblox motoru ile sınırlıdır; yine de Atmosphere/Bloom/Neon/Tween/Particle otomatik eklenir.
- Unity EXE üretimi Unity Hub + lisans gerektirir; proje oluşturulur, EXE üretimi isteğe bağlı ve Unity kuruluysa yapılır.

## Bölüm 3 — Aşamalar ve saatler
- Saat 0-1: Oyun üretici + hakem + tarayıcı testi (BU AŞAMA BİTTİ).
- Saat 1-2: Daha fazla sıfırdan oyun şablonu (Brawl Arena, Battle Royale, Minecraft-sandbox, Among Us, Idle clicker, platformer).
- Saat 2-4: Unity C# üretimi (oyuncu, kamera, düşman, skor) + proje + opsiyonel EXE.
- Saat 4-6: AI işçi boru hattı uçtan uca (proje planı → kod → test → hakem → rapor) ve büyük proje.
- Saat 6-8: Roblox zengin modülleri (yeni oyun türleri + mevcutların grafik yükseltmesi).
- Saat 8-9: Kalibrasyon, hata düzeltme, kurulum/doğrulama.
- Saat 9-10: Final RAPOR (ne oldu, ne yapılmadı, nasıl kullanılır).

## Bölüm 4 — Sıfırdan "bambaşka oyun" akışı (en önemli)
1. Kullanıcı: "şu oyunu yapmak istiyorum: <tarif>"
2. JARVIS: AI'ya oyun tasarımı yaptırır (tür, mekaniğin, kontroller, HUD, kazanma koşulu).
3. AI: tam oynanabilir kodu yazar (Web: tek HTML, Unity: C#, Roblox: Lua).
4. Hakem: 3 varyantı test eder, puanlar, en iyisini seçer.
5. Kullanıcı: bilgisayarında oynar, beğenmezse "şunu değiştir" der, JARVIS düzenler.

## Bölüm 5 — Doğrulama kriterleri
- 1) node --check JS: geçmeli
- 2) headless tarayıcı: canvas var, 0 konsol hatası
- 3) HUD: skor/can görünür, güncellenir
- 4) Oyun döngüsü: requestAnimationFrame çalışır
- 5) Oyun sonu ekrani + yenileme butonu

## Bölüm 6 — Bu oturumda yapılanlar (durum)
- [x] Hakem sistemi (3 varyant, node --check, headless tarayıcı testi, skorlama)
- [x] Tarayıcıda oyun doğrulandı (görsel: neon uzay gemisi, skor 0, can 3, 0 hata)
- [x] JARVIS CODE + PREVIEW, tek pencere, tema sistemi
- [x] Roblox: grafik/animasyon zenginleştirildi
- [x] 100 AI işçi + hakem (pipeline)
- [ ] 10 saatlik tam üretim (rate-limit nedeniyle gerçekçi değil)
- [ ] Tüm oyun türlerine özel motor (AI ile yaklaşık)

## Nasil kullanilir
- JARVIS'e "minecraft benzeri oyun yap" derseniz: oyun üretir, tarayıcıda test eder, hakem en iyisini seçer.
- "şu oyunu yap: <tarif>" → AI sıfırdan üretir.
- "en iyi oyun" → hakem tekrar puanlar, en iyisini açar.
- Rapor: Documents\JARVIS_Atolye\RAPOR_AI_WORKERS.md

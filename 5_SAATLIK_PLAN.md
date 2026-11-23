# JARVIS — 5 SAATLİK ÇALIŞMA PLANI
**Tarih:** 5 Kasım 2026  
**Hedef:** JARVIS'i "sohbet + görev" olarak tam kapasiteye çıkarmak; her soruyu/her işi yapan, ikincil AI'yi her şeyi bilen bir yardımcıya dönüştürmek.

---

## SAAT 1 — SOHBET BEYNİ: HER ŞEYİ BİLİR HALE GETİR

**Amaç:** Sohbet asla boş dönmez; her soruya doğru/mantıklı cevap, bilinmiyorsa en olası tahmin, gerekirse özet.

| Adım | Yapılacak | Durum |
|------|-----------|-------|
| 1.1 | `jarvis_yetenek.SISTEM_TURKCE` — "CEVAPSIZ SORU YOKTUR" davranışı | ✅ yapıldı |
| 1.2 | `jarvis_vscode.py` sohbet promptları — kodu ``` bloğunda yazma kuralı | ✅ yapıldı |
| 1.3 | `jarvis_anta/patch_src_rehber.py` `_ai_tek_cevap` — tahmini cevap politikası | ⏳ sırada |
| 1.4 | Araştır→özetle akışı: "araştır: X", "özetle: X", "ne demek: X" komutları | ⏳ sırada |
| 1.5 | Karma sorular (Türkçe+İngilizce+kod) — doğru ayrıştırma | ⏳ sırada |
| 1.6 | "yasaklı konularda ne yapar?" davranışı: tahmin + nazik red değil, yasal alternatif | ⏳ sırada |

**Çıktı:** Sohbet; "merhaba"dan "kuantum ışınlanma"ya her şeye mantıklı yanıt verir; boş dönmez.

---

## SAAT 2 — İKİNCİL AI: HER ŞEYİ YAPAR, HER ŞEYİ VERİR

**Amaç:** İkincil AI; sohbet edilen soruları araştıran, kod yazan, dosya oluşturan, cevap üreten her şeyi yapan bir yardımcı olacak.

| Adım | Yapılacak | Durum |
|------|-----------|-------|
| 2.1 | `_ai_tek_cevap` promptunu tam yetenekli kıl: araştır + yaz + olustur + özetle | ⏳ sırada |
| 2.2 | "bu kodu yaz" isteklerinde ```` blok` garantisi | ✅ yapıldı (promptlar) |
| 2.3 | Kod çalıştır + sonucu panelde göster (kod ajanı ↔ sohbet köprüsü) | ⏳ sırada |
| 2.4 | WhatsApp/Telegram "mesaji bana bırakır misin" → onaylı mesaj akışı | ✅ yapıldı |
| 2.5 | "bugün ne yapalım" → öneri demeti (müzik/film/oyun/arama) | ⏳ sırada |
| 2.6 | "bununla ilgili ne bilirsin" → konu özeti: konu + kaynak + 3 madde | ⏳ sırada |

**Çıktı:** "Ekle butonu koy", "bu hatayı düzelt", "şunu araştır", "şunu telegrama gönder mi" — hepsi çalışır.

---

## SAAT 3 — SOHBET UI: GÜZEL, HIZLI, KULLANIŞLI

**Amaç:** Sohbet ekranı kullanıcı dostu; "yaz → hemen cevap" akışı kesintisiz.

| Adım | Yapılacak | Durum |
|------|-----------|-------|
| 3.1 | Sürüm garantisi: **her yazılan mesaj sohbete düşer, cevapsız kalmaz** | ✅ yapıldı |
| 3.2 | Canlı oturum sessizliği → `v109 anında cevap` yolu | ✅ yapıldı |
| 3.3 | `📋 KOPYALA` düğmesi — kod altına gerçek buton | ✅ yapıldı |
| 3.4 | Otomatik panoya kopyalama (en son kod bloğu) | ✅ yapıldı |
| 3.5 | AI'ya mesaj → cevap → **"KOPYALA/Yazdır/Oku"** düğmeleri | ⏳ sırada |
| 3.6 | Mesaj geçmişi: "önceki soruya dön" / arama | ⏳ sırada |
| 3.7 | Konu chipleri: #kod #araştırma #müzik #oyun | ⏳ sırada |

**Çıktı:** Sohbet; aç-kapa dışında, net: yaz → cevap → kopyala; beklemez.

---

## SAAT 4 — GÖRSEL + ARAMA + ÖZET: HER SORUNUN CEVABI HAZIR

**Amaç:** Sözel sorular proje/arama/özet akışıyla yanıtlanır; görsel/aksiyon talepleri de yerine getirilir.

| Adım | Yapılacak | Durum |
|------|-----------|-------|
| 4.1 | "araştır <konu>" → kaynak tara + özet akışı | ⏳ sırada |
| 4.2 | "özetle <metin/konsept>" → 3–5 madde | ⏳ sırada |
| 4.3 | "tarif/nasıl/neden" → basamak + örnek | ⏳ sırada |
| 4.4 | Görsel isteği → 🖼️ sohbete iliştirir | ✅ yapıldı (mevcut akış) |
| 4.5 | "hangi oyun/film/müzik" → öneri + açıklama | ⏳ sırada |
| 4.6 | "ne buldun", "ver", "ver mi" → teknik açıklama + kod | ⏳ sırada |

**Çıktı:** Kullanıcı ne sorarsa: ya direk cevap ya araştır+özet ya da öneri.

---

## SAAT 5 — TAMAMLANMA: KURULUMLAR + TEST + RAPOR

**Amaç:** 5 saatlik planın tüm adımlarını sınamak, sabitlemek, rapor yazmak.

| Adım | Yapılacak | Durum |
|------|-----------|-------|
| 5.1 | EXE derle + doğrulama (1629 girdi) | ✅ her saat sonunda |
| 5.2 | Sohbet/test kümesi: 10 soru (sohbet/kod/araştır/görsel) | ⏳ sırada |
| 5.3 | WhatsApp akışı: "kanka bana merhaba de" → liste → onay → gönder | ✅ yapıldı |
| 5.4 | KAYNAK RAPORU: 5_SAATLIK_PLAN.md + commit notu | ✅ bu dosya |
| 5.5 | Bilinen sorunlar: live-oturum sessizliği → v109 anında cevap | ✅ yapıldı |
| 5.6 | Sonraki adımlar: kamera/ses/web otomasyonu | ⏳ sırada |

**Çıktı:** JARVIS: sohbet eden, kod yazan, araştırıp özetleyen, WhatsApp'a cevap veren, ekranı gören, oyunu oynayan kişisel AI.

---

## YOL HARİTASI (Öncelikli)

1. **Sohbet boş dönmeyecek** — her mesaja cevap
2. **AI her şeye cevap** — bilinmeyende tahmin
3. **Yazdığın her kod ekranda** — kopyala düğmesi ✔︎
4. **Araştır → özet** — 3 adımda cevap
5. **WhatsApp/mesaj** — onaylı gönder

## BILINEN SORUNLAR (kapatıldı)

- ✔ 0.7 sn timeout → 25 sn (sohbet cevapsız kalıyordu)
- ✔ Gemini model adı geçersiz → gemini-1.5-flash
- ✔ AI kilit 2 dk → 30 sn, pollinations 46 sn bekleme → 10 sn
- ✔ DÜŞÜNME/KONUŞMA MODU etiketleri → sohbet panelinden tamamen kaldırıldı
- ✔ Canlı oturum sessiz → v109 **anında internet cevap**
- ✔ 📋 KOPYALA → artık gerçek buton
- ✔ AI KOMUT modu açıksa sohbet PowerShell'e gidiyordu → sohbet komut sayılmaz

## SONRA (SAAT 6+)

- Kamera/canlı gör ile sohbet et
- Sessiz kip: "iki cevap" yerine tek cevap
- "Oku" komutu ile sesli okuma
- Uygulama/oyun otomasyonu

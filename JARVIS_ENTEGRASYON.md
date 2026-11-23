# JARVIS ENTEGRASYON NOTU — OYUN MERKEZİ (Aşama 0 çıktısı)

Bu belge, `OYUN MERKEZİ` projesinin kullanıcının Windows'taki **JARVIS** masaüstü
programının oyun kütüphanesine nasıl ekleneceğini tarif eder. Keşif sırasında
bulunan **gerçek** katalog düzenine dayanır; hiçbir bilgi uydurulmamıştır.

---

## 1. Keşif özeti (bulunan gerçekler)

### 1.1 NeonCity projesi (referans oyun)
- **Kaynak klasör:** `games_src/neoncity/`
- **Motor:** Godot, `config/features=PackedStringArray("4.7", "Forward Plus")`
  → **Godot 4.7, Forward+** işleyici.
- **Ana sahne:** `res://scenes/ana.tscn`
- **Otoload:** tek otoload → `Ayarlar="*res://scripts/ayarlar.gd"`
- **Pencere:** 1600×900 (`viewport_width/height`)
- **Testler:** `games_src/neoncity/tests/` (`test.tscn` headless doğrulama,
  `shot.tscn` ekran görüntüsü/FPS testi)
- **Export:** `export_presets.cfg` → `Windows Desktop`, hedef
  `../../games/neoncity/NeonCity.exe`, **`binary_format/embed_pck=true`**
  (tek dosya EXE), `exclude_filter="tests/*"`, şirket adı `JARVIS Atolye`,
  ürün adı `NeonCity`, mimari `x86_64`.

### 1.2 JARVIS'in EXE oyunları nasıl tanıdığı (KATALOG MOTORU)
JARVIS'in oyun kütüphanesi **dosyadan okunmaz; klasör taramasıyla üretilir.**
Motor dosyası: **`jarvis_oyun_katalog.py`**.

İlgili fonksiyon: `exe_oyunlari()` — şunu yapar:
1. `_exe_kokleri()` ile şu klasörlerdeki **`games`** alt klasörlerini tarar:
   - `JARVIS.exe`'nin yanındaki `games/` (PyInstaller kurulumu)
   - `sys.argv[0]` yanındaki `games/` (tek dosya sürümü)
   - `os.getcwd()/games/`
   - modülün kendi yanındaki `games/`
   - **`~/Documents/JARVIS_Atolye/games/`** (kullanıcının atölyesi)
2. Her `<kok>/games/<oyun_klasoru>/` altındaki `.exe` dosyalarını bulur.
   Aynı adı taşıyan EXE tercih edilir: `f1_yaris/f1_yaris.exe`.
3. **Görünen ad**, EXE dosya adından üretilir: alt çizgi boşluğa çevrilir,
   `.exe` atılır ve `.title()` ile ilk harfler büyütülür:
   `OyunMerkezi.exe` → **"Oyunmerkezi"**.
4. **Etiketler** iki katmanlıdır:
   - Otomatik: `['[exe]', 'yerel', 'exe', '3d', 'godot']`
   - Oyuna özel kategori: sözlük **`EXE_KATEGORI`** (dosya başına ~satır 437):
     ```python
     EXE_KATEGORI = {
         'neoncity': ['aksiyon', 'acik dunya', 'araba', '3inci sahs'],
         'f1_yaris': ['yaris', 'araba', 'spor'],
     }
     ```
     Anahtar, **klasör adının küçük harflidir** (`d.lower()`).
5. Kayıt `_kayit(ad, etiket, 'exe', yol=...)` biçiminde üretilir ve panelde
   listelenir.

### 1.3 Oyun nasıl başlatılıyor (AÇ butonu)
Aynı dosyadaki `ac(kayit)` fonksiyonu (satır ~668):
- `kayit['yol']` `.exe` ise oyun **ayrı süreç olarak** başlatılır:
  `subprocess.Popen([yol], cwd=klasor, close_fds=True,
  creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)`
- Yani JARVIS oyunu **bağımsız bir süreç** olarak açar; JARVIS oyunla
  ilgilenmez, oyun kapanınca JARVIS etkilenmez. Oyuna **hiçbir parametre
  gönderilmez.** → Bölüm 0.6'daki "parametre gelmediğinde de sorunsuz açılma"
  şartı zaten karşılanır.

### 1.4 `roblox_3d` girişine dokunulmadı
`exe_oyunlari()` tarama tabanlıdır; katalogda sabit bir `roblox_3d` kaydı
**bulunmamaktadır** (grep ile doğrulandı, boş sonuç). Bu, panelin başka bir
kaynağından (HTML atölye üretimi ya da manuel) geliyor olabilir. **Biz bu girişe
dokunmuyoruz.** Yeni oyunumuz farklı bir klasör adı ve farklı bir EXE adı
kullanacağı için çakışma olmaz.

### 1.5 Godot sürümü eşitlendi
NeonCity **Godot 4.7** kullanıyor. Sistemde kurulu konsol binary'si
`tools/godot/Godot_v4.7.2-stable_win64_console.exe` → **4.7.2**, aynı 4.7
serisi. OYUN MERKEZİ de **Godot 4.7 (Forward+)** ile geliştirilecek. Fark yok,
ek karar gerekmedi.

---

## 2. OYUN MERKEZİ için entegrasyon planı

### 2.1 Klasör ve EXE yolu
Aynı düzende, yani `games/<klasor>/<oyun>.exe`:

| Öğe | Değer |
|---|---|
| Kaynak klasör (geliştirme) | `games_src/oyun_merkezi/` |
| Atölye klasörü (geliştirme) | `~/Documents/JARVIS_Atolye/oyun_merkezi/` |
| JARVIS kütüphanesi klasörü | `<JARVIS>/games/roblox_merkez/` |
| Ana EXE yolu | `<JARVIS>/games/roblox_merkez/OyunMerkezi.exe` |

> **ÖNEMLİ — EXE adı ve JARVIS'te görünen ad ayrımı:**
> `exe_oyunlari()` görünen adı EXE dosya adından üretir (`OyunMerkezi.exe` →
> "Oyunmerkezi"). Bu, JARVIS'te "Roblox" olarak görünmesini sağlamaz.
> İki seçenek var:
>
> **A (önerilen, temiz):** JARVIS'e `roblox_merkez` klasörünün adını
> ("Roblox") gösteren küçük bir `EXE_KATEGORI` + görünen-ad sözlüğü eklemek.
> `jarvis_oyun_katalog.py` içinde tek satırlık bir sözlük:
> ```python
> EXE_KATEGORI['roblox_merkez'] = ['aksiyon', 'macera', '3d', 'cok oyunculu', 'platform']
> # + görünen ad sözlüğü (varsa); yoksa 2 satırlık yeni bir eşleme:
> EXE_AD = {'roblox_merkez': 'Roblox'}   # panele yazılacak etiket
> ```
> ve `exe_oyunlari()` içinde `ad = EXE_AD.get(d.lower(), ad)`.
>
> **B (JARVIS'e dokunmadan):** Klasör ve EXE adını doğrudan `roblox` yapmak
> (`games/roblox/roblox.exe`) → panelde "Roblox" görünür. Ama `roblox_3d`
> girişiyle karışabilir; bu yüzden **uygunsuz**.
>
> **Kural gereği `roblox_3d`'ye dokunmadan "Roblox" etiketini istiyorsak
> A seçeneğini uygulayacağız.** JARVIS kodunda değişiklik gerekiyor; bu,
> Bölüm 0.3'teki "yeni giriş" kuralıyla uyumludur (girişin kimliği
> `roblox_merkez` olur, `roblox_3d`'ye dokunulmaz).

### 2.2 Katalog kaydı (tam örnek — A seçeneği için)

`jarvis_oyun_katalog.py` içine eklenecek **tek blok**:

```python
# --- OYUN MERKEZİ (Roblox tarzi mini oyun platformu) — yedek satirlar ---
EXE_KATEGORI['roblox_merkez'] = [
    'aksiyon', 'macera', '3d', 'cok oyunculu', 'platform',
]
EXE_AD = {'roblox_merkez': 'Roblox'}     # panelde gorunen ad
```

Ve `exe_oyunlari()` içindeki `ad = os.path.splitext(...)` satırından sonra:

```python
ad = EXE_AD.get(d.lower(), ad)           # OYUN MERKEZI -> 'Roblox'
```

**Sonuç:** Panelde `Roblox` başlığı, etiketler `[exe] yerel exe 3d godot
aksiyon macera cok oyunculu platform` ile görünür; AÇ'ya basınca
`games/roblox_merkez/OyunMerkezi.exe` bağımsız süreç olarak başlar.

### 2.3 Godot export ayarı (`export_presets.cfg` özeti)

```ini
[preset.0]
name="Windows Desktop"
platform="Windows Desktop"
export_path="../../games/roblox_merkez/OyunMerkezi.exe"
exclude_filter="tests/*"

[preset.0.options]
binary_format/embed_pck=true          # tum kaynaklar EXE icine (Bolum 6/H)
binary_format/architecture="x86_64"
codesign/enable=false
application/modify_resources=true
application/file_version="0.1.0.0"
application/product_version="0.1.0.0"
application/company_name="JARVIS Atolye"
application/product_name="Oyun Merkezi"
application/file_description="Oyun Merkezi - cok oyunculu mini oyun platformu"
application/copyright="Orijinal yapim"
application/icon="res://assets/icons/ikon.ico"
```

> `embed_pck=true` sayesinde **tüm oyunlar, sahneler, sesler tek EXE'nin
> içindedir** → Bölüm 0.6 ve 1.1'deki "aynı dosya, aynı kütüphane" şartı
> garanti altına alınır. JARVIS'ten bağımsız çalışır.

### 2.4 Bağımsızlık ve güvenli kapanış (Bölüm 0.6 / 0.7)
- JARVIS oyunu `DETACHED_PROCESS` ile başlatır → oyun **çökse bile** JARVIS
  penceresi ve kütüphanesi bozulmaz. Bu, JARVIS'in kendi kodundadır; biz
  değiştirmiyoruz, sadece doğruladık.
- Oyun JARVIS'in dosyalarına **hiç dokunmaz**; kendi kaydı
  `user://kayit.json` altındadır (`config/name="OyunMerkezi"`), NeonCity'nin
  kaydıyla (`AppData/Roaming/Godot/app_userdata/NeonCity/`) **karışmaz.**
- JARVIS parametre göndermez; oyun parametresiz normal şekilde açılır.

### 2.5 Etiketler (Bölüm 0.5 — kesinleştirildi)
JARVIS panel kategori düğmeleri `EXE_KATEGORI` etiketleriyle eşleşir.
Kesin etiket seti: **`aksiyon`**, **`macera`** (kategori düğmeleri),
**`3d`**, **`cok oyunculu`**, **`platform`** (etiketler). Açıklamada
"çok oyunculu mini oyun platformu" ifadesi geçer.

---

## 3. Yapılmayacaklar (netleştirildi)
- `roblox_3d` girişine **dokunulmayacak** (silinmeyecek, adı değiştirilmeyecek).
- Roblox'un logosu, yazı tipi, renkleri veya herhangi bir varlığı
  **kullanılmayacak** (Bölüm 0.3 / Kural 2).
- Gerçek para, mikro ödeme, loot box **olmayacak** (Kural 1).

---

## 4. Uygulanan kayıt (tamamlandı)
`jarvis_oyun_katalog.py` içindeki `EXE_KATEGORI` sözlüğüne yeni kimlik
eklenmiştir (`roblox_3d` girişine dokunulmadan):

```python
'roblox_merkez': ['aksiyon', 'macera', 'platform', 'cok oyunculu'],
```

Katalog taramasının doğrulanmış çıktısı (`tools/py312/python.exe`):

```
Roblox | 3d,[exe],aksiyon,cok oyunculu,exe,godot,macera,platform,yerel
       | ...\games\roblox_merkez\roblox.exe
```

Yani liste satırı şu şekilde görünür:

```
Roblox    [exe] 3d aksiyon macera platform cok oyunculu yerel godot
```

**Dosya yerleşimi (kesin):**

| Ne | Yol |
|---|---|
| Kaynak proje | `games_src/oyun_merkezi/` |
| Dışa aktarılan .exe | `games/roblox_merkez/roblox.exe` |
| JARVIS kaydı | `jarvis_oyun_katalog.py` → `EXE_KATEGORI['roblox_merkez']` |
| Dokunulmayan giriş | `roblox_3d` (tohum listesinde, aynen duruyor) |

**Not:** Katalog modülü JARVIS.exe'nin içine derlenmiştir. Yeni etiketlerin
panelde görünmesi için bir kez `python tools/derle.py` (JARVIS.exe'yi kapatıp
yeniden paketler) çalıştırılmalıdır. .exe dosyası `games/` klasöründe olduğu
sürece **"Roblox"** satırı yeniden derleme olmadan da listede görünür;
sadece AKSİYON/MACERA kategori düğmeleri için derleme gerekir.

**Godot sürümü:** 4.7.2 (NeonCity ile aynı) — eşitlendi, karar gerekmedi.

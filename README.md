# TCDD Bilet Takip

TCDD Taşımacılık e-bilet sisteminde belirli bir rota ve tarih için uygun trenleri takip eden küçük bir araç.

Bu proje:

- TCDD verisini okuyup uygun seferleri arar
- Saat, tren tipi ve sınıf filtresi uygular
- Eşleşen sonuç çıkarsa terminale yazar
- İsterseniz `ntfy` ile telefonunuza bildirim gönderir
- İsterseniz tarayıcıdan kullanabileceğiniz basit bir kontrol paneli sunar

Bu proje bilet satın almaz. Rezervasyon yapmaz. Koltuk seçmez. Giriş yapmaz. Ödeme otomasyonu yapmaz. Yalnızca arama ve bildirim için tasarlanmıştır.

## Gereksinimler

- Windows
- Python 3.11+
- İnternet bağlantısı

## Kurulum

Depoyu indirdikten sonra proje klasöründe:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Hızlı Başlangıç

### 1. Web panelini aç

```powershell
python tcdd_ui.py
```

Tarayıcıda açın:

```text
http://127.0.0.1:5000/
```

Panel üzerinden:

- kalkış istasyonu
- varış istasyonu
- tarih
- net saat veya saat aralığı
- tren tipi filtresi
- sınıf filtresi
- kontrol aralığı
- `ntfy` ayarları

girilebilir.

İstasyon listesi TCDD verisinden çekilir. Arama kutularında yazarak istasyon seçilebilir.

### 2. Tek sefer arama yap

Panelde `Tek sefer ara` butonuna basın.

Sonuçlar sağ tarafta görünür:

- kalkış saati
- tren adı
- sınıf
- müsaitlik bilgisi

### 3. Sürekli takibi başlat

Panelde `Başlat` butonuna basın.

Watcher belirlediğiniz aralıkla tekrar tekrar arama yapar. Eşleşen uygun sonuç bulursa:

- panelde sonucu gösterir
- terminale yazar
- `ntfy` ayarlıysa telefona bildirim gönderir

Duraklatmak için `Durdur` butonunu kullanın.

## Komut Satırından Kullanma

Aracı panel olmadan da çalıştırabilirsiniz.

### 1. Örnek config oluştur

```powershell
Copy-Item config.example.toml config.toml
```

`config.toml` dosyasını düzenleyin.

Örnek alanlar:

- `departure_station`: kalkış istasyonu
- `arrival_station`: varış istasyonu
- `date`: yolculuk tarihi
- `preferred_departure_time`: tam saat eşleşmesi
- `departure_time_from` / `departure_time_to`: saat aralığı
- `train_keyword`: örnek `YHT`
- `seat_class_keyword`: örnek `Ekonomi`
- `check_interval_seconds`: kaç saniyede bir kontrol edileceği
- `ntfy_topic`: telefon bildirimi için konu adı
- `ntfy_server`: genelde `https://ntfy.sh`

### 2. Tek sefer çalıştır

```powershell
python tcdd_watcher.py --config config.toml --once
```

### 3. Sürekli çalıştır

```powershell
python tcdd_watcher.py --config config.toml
```

### 4. Bildirim göndermeden test et

```powershell
python tcdd_watcher.py --config config.toml --once --dry-run
```

## `ntfy` ile Telefon Bildirimi

Telefonunuza bildirim almak için `ntfy` kullanabilirsiniz.

### 1. Telefona `ntfy` uygulamasını kurun

- Android veya iPhone için `ntfy` uygulamasını yükleyin

### 2. Bir topic belirleyin

Örnek:

```text
umut-tcdd-bilet-12345
```

### 3. Uygulamada bu topic'e abone olun

### 4. Panelde veya `config.toml` içinde şu alanları doldurun

```text
ntfy_topic = "umut-tcdd-bilet-12345"
ntfy_server = "https://ntfy.sh"
```

### 5. Test bildirimi gönderin

Panelde `Test gönder` butonunu kullanabilirsiniz.

PowerShell'den elle test etmek isterseniz:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://ntfy.sh/umut-tcdd-bilet-12345" `
  -Body "Merhaba"
```

## Filtreleme Mantığı

Arama sonucu geldikten sonra proje şu filtreleri uygular:

- tarih
- net saat veya saat aralığı
- tren tipi anahtar kelimesi
- sınıf anahtar kelimesi
- müsaitlik durumu

Örnek:

- `train_keyword = "YHT"` ise yalnızca YHT geçen trenler kalır
- `seat_class_keyword = "Ekonomi"` ise ekonomi sınıfı uygun olanlar kalır

## Dosyalar

- `tcdd_ui.py`: Flask tabanlı web paneli
- `tcdd_watcher.py`: çekirdek arama ve watcher mantığı
- `config.example.toml`: örnek ayar dosyası
- `config.toml`: sizin ayarlarınız
- `TCDD_SITE_MAP.md`: TCDD sayfa davranışı ve gözlem notları

## Bilinen Sınırlar

- TCDD tarafındaki API veya sayfa davranışı değişirse araç güncelleme isteyebilir
- Sonuç bilgisi tamamen TCDD tarafından dönen anlık veriye bağlıdır
- `ntfy` kullanımı için internet bağlantısı gerekir
- Bu araç TCDD hesabı ile işlem yapmaz

## Sorun Giderme

### Panel açılmıyorsa

```powershell
python tcdd_ui.py
```

Sonra `http://127.0.0.1:5000/` adresini kontrol edin.

### İstasyon listesi gelmiyorsa

İnternet bağlantısını ve TCDD tarafına erişimi kontrol edin.

### Bildirim gelmiyorsa

- `ntfy_topic` boş olmasın
- telefonda doğru topic'e abone olun
- panelden `Test gönder` deneyin
- `ntfy_server` değerinin doğru olduğunu kontrol edin

### Terminalde sonuç yok ama TCDD sitesinde var görünüyorsa

Genelde sebep filtrelerin fazla dar olmasıdır:

- saat aralığı
- `train_keyword`
- `seat_class_keyword`

Önce filtreleri boşaltıp tekrar deneyin.

## Lisans ve Kullanım

Bu repo kişisel takip amacıyla hazırlanmıştır. Kullanım sorumluluğu size aittir.

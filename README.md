# TCDD Bilet Takip

> Not: Bu proje yapay zeka desteğiyle oluşturulmuş ve geliştirilmiştir.

TCDD Taşımacılık e-bilet sisteminde belirli bir rota ve tarih için uygun trenleri takip eden küçük bir terminal aracıdır.

Bu proje:

- TCDD verisini okuyup uygun seferleri arar
- Saat, tren tipi ve sınıf filtresi uygular
- Eşleşen sonuç çıkarsa terminale yazar
- İsterseniz `ntfy` ile telefonunuza bildirim gönderir

Bu proje bilet satın almaz. Rezervasyon yapmaz. Koltuk seçmez. Giriş yapmaz. Ödeme otomasyonu yapmaz. Yalnızca arama ve bildirim için tasarlanmıştır.

## Gereksinimler

- Windows
- Python 3.11+
- İnternet bağlantısı

## Kurulum

Proje klasöründe:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Windows'ta zaman dilimi verisi eksikse ayrıca şu komut da çalıştırılabilir:

```powershell
pip install tzdata
```

## Kullanım

Önce [config.toml](C:/Users/Umut/Desktop/TCDD-BILET/config.toml) dosyasını düzenleyin.

Başlıca alanlar:

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

Tek sefer arama:

```powershell
python tcdd_watcher.py --config config.toml --once
```

Sürekli izleme:

```powershell
python tcdd_watcher.py --config config.toml
```

Bildirim göndermeden test:

```powershell
python tcdd_watcher.py --config config.toml --once --dry-run
```

Eşleşme bulunduğunda araç:

- terminale sonucu yazar
- `ntfy` ayarlıysa bildirim gönderir

## `ntfy` ile Telefon Bildirimi

Telefonunuza bildirim almak için `ntfy` kullanabilirsiniz.

Örnek ayar:

```toml
ntfy_topic = "umut-tcdd-bilet-12345"
ntfy_server = "https://ntfy.sh"
```

Elle test için:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://ntfy.sh/umut-tcdd-bilet-12345" `
  -Body "Merhaba"
```

## Dosyalar

- `tcdd_watcher.py`: çekirdek arama ve watcher mantığı
- `config.toml`: sizin ayarlarınız

## Sorun Giderme

İstasyon bulunamıyorsa:

- istasyon adını TCDD’de göründüğü gibi yazın
- filtreleri sadeleştirip tekrar deneyin

Bildirim gelmiyorsa:

- `ntfy_topic` boş olmasın
- telefonda doğru topic’e abone olun
- `ntfy_server` doğru olsun

Terminalde sonuç yoksa:

- saat aralığını genişletin
- `train_keyword` filtresini boşaltın
- `seat_class_keyword` filtresini boşaltın

## Kullanım Notu

Bu repo kişisel takip amacıyla hazırlanmıştır. Kullanım sorumluluğu size aittir.

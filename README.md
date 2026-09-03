# Spor Toto AI

Bu proje haftalık Spor Toto 15 maç listesini alır, GitHub Actions ile veri üretir ve GitHub Pages üzerinde yayınlar.

Ana çalışma mantığı üç parçadır:

1. **Liste/veri üretimi:** Resmî Spor Toto bülteni veya yedek kaynak üzerinden 15 maçlık kupon listesi oluşturulur.
2. **Tahmin ve risk üretimi:** API-Football oran/fixture verisi ve/veya football-data.org geçmiş maç verisinden model üretilir; son 5 form ve en fazla son 10 H2H her hafta yeniden hesaplanır. Tahmin sitesi/oynanma yüzdesi verileri konsensüs, model ayrışması ve tuzak favori sinyali olarak kullanılır.
3. **Dar kupon öncelikli karar politikası:** Önce gerçek oynanacak dar kupon, sonra onun üzerine sanal geniş kontrol kuponu üretilir.

> Not: Bu proje kesin sonuç tahmini üretmez. Amaç karar disiplinini, kolon verimliliğini ve hafta sonu kalibrasyonunu iyileştirmektir.

## Ana felsefe

Yeni ana yaklaşım:

```text
Önce dar kupon, sonra geniş sanal kontrol kuponu.
```

Dar kupon gerçek parayla oynanan ana üründür. Bu yüzden haftalık başarı önce dar kupon üzerinden ölçülür. Geniş kupon ise gelir üretmeyen, sadece modelin radarındaki ek ihtimalleri takip eden sanal kontrol kuponudur.

## Karar politikası

Üçlü tercih kullanılmaz:

```text
1X2 yasak
```

Geçerli tercihler:

```text
1, X, 2, 1X, X2, 12
```

Dar kupon hedefi:

```text
7-8 çift + kalan maçlar tek = 128-256 kolon
```

Geniş sanal kupon hedefi:

```text
Dar kupon + ek ihtimaller = 11 çift + 4 tek = 2.048 kolon
```

Ayrıntılı karar dosyası: [`docs/DECISION_POLICY.md`](docs/DECISION_POLICY.md)

## Tahmin sitesi / oynanma yüzdesi girişi

`data/consensus.csv` dosyası isteğe bağlıdır. Bu dosyaya Spor Toto, Nesine, Bilyoner, Misli, Hedef15 veya benzer kaynaklardan 1-X-2 yüzdeleri girilebilir.

Bu veriler maç sonucunu kopyalamak için değil; konsensüs, tuzak favori, düşük yüzdeli ters taraf ve kolon dağılımı sinyali için kullanılır. Bayi oynanma yüzdeleri tek bir kitle sinyali kabul edilir. `model_a`, `model_b` ve `model_c` alanları farklı bağımsız tahmin modelleri için ayrılmıştır; adları ve veri tarihi de CSV'ye yazılır. Bağımsız modeller ana olasılığa en fazla %25 ağırlıkla katılır.

## Haftalık form ve H2H

Model her çalıştığında yalnızca maç tarihinden önceki karşılaşmaları kullanarak son 5 formu, iç/dış saha örneklemini ve iki takım arasındaki en fazla son 10 maçı yeniden hesaplar. Bu özetler her maçın `model_sample.recent_form` ve `model_sample.h2h` alanlarında yayımlanır. Ağustos-eylül döneminde H2H etkisi düşürülür; güncel kadro ve formun önüne geçirilmez.

## Dosya yapısı

```text
sportoto-ai/
├── .github/workflows/update-coupon.yml  # Haftalık Spor Toto listesini yeniler
├── .github/workflows/update-data.yml    # Model verisini ve JSON çıktısını üretir
├── scripts/update_coupon.py             # 15 maçlık kupon listesini oluşturur
├── scripts/fetch_data.py                # API-Football / football-data verisinden model üretir
├── scripts/apply_decision_policy.py     # Dar öncelikli, üçlüsüz kupon politikasını uygular
├── scripts/reset_consensus.py           # Yeni haftada konsensüs şablonunu sıfırlar
├── data/coupon.csv                      # Bağlayıcı 15 maç listesi
├── data/predictions.csv                 # Manuel geniş/dar tercih alanı
├── data/consensus.csv                   # Tahmin sitesi / oynanma yüzdesi opsiyonel girişi
├── data/matches.json                    # Ana JSON çıktı
├── docs/index.html                      # GitHub Pages paneli
├── docs/data/matches.json               # Panelin okuduğu JSON
└── requirements.txt
```

## Kurulum

GitHub'da repository secret ekleyin:

```text
Settings → Secrets and variables → Actions → New repository secret
```

Secret adı:

```text
FOOTBALL_DATA_TOKEN
```

Değer: football-data.org API anahtarı.

API-Football yeniden aktifse ikinci secret'ı ekleyin:

```text
API_FOOTBALL_KEY
```

Değer: API-Football / API-Sports anahtarı.

API-Football Free planinda dogrudan `date` ile ileriki gun fiksturleri bazen kapali olabilir. Bu durumda model, eski calisan yontemi de kullanir: ilgili `league + season` fikstur havuzunu cekip kupondaki takimlari ve tarihleri bu havuzdan eslestirir.

GitHub Pages için:

```text
Settings → Pages → Build and deployment → Source → GitHub Actions
```

## Yerel deneme

PowerShell'de proje klasöründe:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FOOTBALL_DATA_TOKEN="ANAHTARINIZ"
$env:API_FOOTBALL_KEY="ANAHTARINIZ"
python scripts/update_coupon.py
python scripts/reset_consensus.py
python scripts/fetch_data.py
python scripts/apply_decision_policy.py
```

## Haftalık çalışma döngüsü

- **Salı:** geçen hafta sonuçlarıyla takım notları, son form ve H2H güncellenir; ilk dar taslak çıkarılır.
- **Çarşamba, perşembe:** tahmin sitesi/model konsensüsü, oynanma yüzdeleri, oran, kadro ve haberlerle dar taslak kalibre edilir.
- **Cuma:** önce gerçek oynanacak dar kupon, sonra sanal geniş kontrol kuponu belirlenir.
- **Cumartesi, pazar, pazartesi:** yeni tahmin üretilmez; cuma günü oynanan dar kupon ve sanal geniş kupon takip edilir.
- **Salı:** yeni haftanın kuponu alınır ve döngü yeniden başlar.

## Haftalık kalibrasyon

Başarı ölçümleri sıralaması:

1. Dar kupon gerçek başarı oranı.
2. Dar kupondaki tek başarı oranı.
3. Dar kupondaki çift başarı oranı.
4. Dar kuponun yanlış sildiği ihtimaller.
5. Geniş sanal kuponun yakaladığı ama dara taşınmayan ihtimaller.
6. Türkiye / Avrupa ayrı performans.
7. Tuzak favori ve daraltma hataları.
8. Kolon verimliliği.

Sonradan yapılan tahmin revizyonları başarı hesabına katılmaz. Cuma günü oynanan dar kupon gerçek referans, geniş kupon sanal/model referansı olarak ayrı değerlendirilir.
